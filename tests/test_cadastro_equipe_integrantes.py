"""
Cadastrar equipe e integrantes em um fluxo, com cadastro próprio de quem não tem conta (BE-S5-02).

Cobre usuários existentes e novos, o link de cadastro por convite (uso único, validade, erros
400/409/422), a conta pendente que aceita o convite, a idempotência do POST /equipes, concorrência
e segurança do token. Os testes gravam no banco de verdade; a fixture `fluxo` apaga o que cria
(usuários e e-mails saem pelas fixtures de conftest.py).
"""

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from tests.helpers_email import emails_de
from tests.test_convites import com_token
from tests.test_equipes_categoria import CenarioCategoria
from tests.test_migrations import novo_hackathon, novo_usuario, rodar
from tests.test_migrations import sql as sql_na_transacao

SENHA_NOVA = "minhasenha123"
COMPROVANTE = "https://res.cloudinary.com/demo/comprovante.pdf"
INVALIDO = {"detail": "Link de convite inválido, vencido ou já utilizado."}


class CenarioFluxo(CenarioCategoria):
    def __init__(self, sql, usuario_no_banco, novo_email):
        super().__init__(sql, usuario_no_banco, novo_email)
        self.usuarios_novos: list[str] = []

    def token_do_email(self, email: str) -> str:
        """O token puro só existe no e-mail enviado, no fragmento do link de cadastro."""
        corpo = emails_de(self.sql, email, "CONVITE_EQUIPE")[-1]["corpo_texto"]
        achado = re.search(r"/cadastro#convite=([\w-]+)", corpo)
        assert achado, corpo
        return achado.group(1)

    def criar_com_chave(self, client, chave, quem=None, **campos):
        return client.post(
            "/equipes",
            headers={**com_token((quem or self.criador)["id"]), "Idempotency-Key": chave},
            json={"hackathon_id": str(self.hackathon_id), **campos},
        )

    def consultar(self, client, token):
        return client.post("/auth/cadastro/convite/consulta", json={"token": token})

    def cadastrar(self, client, token, **campos):
        corpo = {"token": token, "senha": SENHA_NOVA, **campos}
        return client.post("/auth/cadastro/convite", json=corpo)

    def equipe_com_novato(self, client, **extra) -> tuple[dict, dict, str]:
        """Equipe de três pessoas: duas ainda sem conta. Devolve a equipe, o convite do primeiro
        novato (com o e-mail dele) e o token do link de cadastro dele."""
        novo = self.indicado("Nina Nova")
        equipe = self.criar_ok(client, integrantes=[novo, self.indicado("Outra Nova")], **extra)
        return equipe, novo, self.token_do_email(novo["email"])

    def usuario_por_email(self, email: str) -> dict | None:
        achados = self.sql("SELECT * FROM usuarios WHERE lower(email) = lower(:e)", e=email)
        return achados[0] if achados else None

    def equipes_do_criador(self) -> int:
        return self.sql(
            "SELECT count(*) AS n FROM equipes WHERE criada_por = :u", u=self.criador["id"]
        )[0]["n"]

    def limpar(self):
        for h in self.hackathons:
            self.sql("DELETE FROM comprovantes_vinculo WHERE hackathon_id = :h", h=h)
        super().limpar()


@pytest.fixture
def fluxo(sql, usuario_no_banco, novo_email):
    cenario = CenarioFluxo(sql, usuario_no_banco, novo_email)
    yield cenario
    cenario.limpar()


# --- Equipe com usuários existentes e novos, em uma operação ---


def test_equipe_com_conta_existente_e_pessoa_sem_conta(client, fluxo, sql):
    existente, item_existente = fluxo.com_conta(nome="Eva Existente")
    novo = fluxo.indicado("Nina Nova")

    equipe = fluxo.criar_ok(client, integrantes=[item_existente, novo])

    assert equipe["situacao"] == "EM_FORMACAO" and equipe["homologada_em"] is None
    assert len(fluxo.membros(equipe["id"])) == 1  # nenhum convidado vira integrante sem aceitar
    com_conta = fluxo.convite_de(equipe["id"], existente["email"])
    sem_conta = fluxo.convite_de(equipe["id"], novo["email"])
    # Conta existente: o convite é associado à conta e não há link de cadastro
    assert com_conta["usuario_id"] == existente["id"]
    assert com_conta["token_hash"] is None and com_conta["token_expira_em"] is None
    # Sem conta: convite individual, com link de uso único e validade
    assert sem_conta["usuario_id"] is None
    assert re.fullmatch(r"[0-9a-f]{64}", sem_conta["token_hash"])
    assert sem_conta["token_expira_em"] > datetime.now(UTC).replace(tzinfo=None)
    assert sem_conta["token_utilizado_em"] is None
    # O líder não criou conta nem definiu senha de ninguém
    assert fluxo.usuario_por_email(novo["email"]) is None


def test_email_de_quem_tem_conta_vai_para_convites_e_de_quem_nao_tem_traz_o_link(
    client, fluxo, sql
):
    existente, item_existente = fluxo.com_conta()
    novo = fluxo.indicado()
    fluxo.criar_ok(client, integrantes=[item_existente, novo])

    [do_existente] = emails_de(sql, existente["email"], "CONVITE_EQUIPE")
    [do_novo] = emails_de(sql, novo["email"], "CONVITE_EQUIPE")

    assert "/convites" in do_existente["corpo_texto"]
    assert "#convite=" not in do_existente["corpo_texto"]
    assert "/cadastro#convite=" in do_novo["corpo_texto"]
    assert (
        "Criar meu acesso" in do_novo["corpo_texto"] and "Criar meu acesso" in do_novo["corpo_html"]
    )
    # O banco guarda só o hash: o token puro não está em nenhuma coluna do convite
    token = fluxo.token_do_email(novo["email"])
    convite = fluxo.sql("SELECT * FROM convites WHERE lower(email) = lower(:e)", e=novo["email"])[0]
    assert convite["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in {str(v) for v in convite.values()}


def test_convite_avulso_e_composicao_substituida_tambem_geram_o_link(client, fluxo, sql):
    equipe = fluxo.criar_ok(client, integrantes=[fluxo.indicado(), fluxo.indicado()])
    avulso = fluxo.novo_email()
    resposta = client.post(
        f"/equipes/{equipe['id']}/convites",
        json={"nome": "Avulsa", "email": avulso},
        headers=com_token(fluxo.criador["id"]),
    )
    assert resposta.status_code == 201, resposta.text
    novos = [fluxo.indicado("Carla"), fluxo.indicado("Dani")]

    troca = fluxo.substituir(client, equipe["id"], categoria="ESTUDANTES", integrantes=novos)

    assert troca.status_code == 200, troca.text
    assert fluxo.token_do_email(avulso)
    assert all(fluxo.token_do_email(n["email"]) for n in novos)


# --- Cadastro próprio pelo link do convite ---


def test_cadastro_pelo_link_cria_conta_pendente_com_a_propria_senha(client, fluxo, sql):
    equipe, novo, token = fluxo.equipe_com_novato(client)

    consulta = fluxo.consultar(client, token)
    assert consulta.status_code == 200, consulta.text
    assert consulta.json()["email"] == novo["email"].lower()
    assert consulta.json()["nome"] == "Nina Nova"
    assert consulta.json()["equipe_nome"] is None  # a equipe foi criada sem nome
    assert consulta.json()["tipo_integrante"] == "ESTUDANTE"

    resposta = fluxo.cadastrar(client, token, instituicao="UFPA", curso="SI", periodo=4)

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["email"] == novo["email"].lower() and corpo["nome"] == "Nina Nova"
    assert corpo["papel"] == "PARTICIPANTE" and corpo["situacao_conta"] == "PENDENTE"
    assert corpo["email_confirmado_em"] is not None
    assert "senha" not in resposta.text and "hash" not in resposta.text
    usuario = fluxo.usuario_por_email(novo["email"])
    assert usuario["senha_hash"].startswith("$argon2")  # a senha é da própria pessoa
    convite = fluxo.convite_de(equipe["id"], novo["email"])
    assert convite["usuario_id"] == usuario["id"]
    assert convite["token_utilizado_em"] is not None and convite["status"] == "PENDENTE"
    assert (
        fluxo.sql("SELECT 1 FROM comprovantes_vinculo WHERE usuario_id = :u", u=usuario["id"]) == []
    )
    login = client.post("/auth/login", json={"email": novo["email"], "senha": SENHA_NOVA})
    assert login.status_code == 200, login.text


def test_conta_pendente_aceita_o_convite_e_a_equipe_segue_nao_homologada(client, fluxo, sql):
    equipe, novo, token = fluxo.equipe_com_novato(client)
    criada = fluxo.cadastrar(client, token).json()
    pessoa = {"id": criada["id"], "email": novo["email"]}
    cabecalho = com_token(criada["id"])

    # A conta ainda espera a conferência do comprovante, mas já vê e responde ao convite (RN25)
    assert client.get("/convites/meus", headers=cabecalho).status_code == 200
    vigentes = client.get(f"/hackathons/{fluxo.hackathon_id}/termos/vigentes", headers=cabecalho)
    assert vigentes.status_code == 200
    aceite = fluxo.aceitar_como(client, pessoa, equipe["id"], novo["email"])

    assert aceite.status_code == 200, aceite.text
    assert str(criada["id"]) in {str(u) for u in fluxo.membros(equipe["id"])}
    assert fluxo.usuario_por_email(novo["email"])["situacao_conta"] == "PENDENTE"
    atual = client.get(f"/equipes/{equipe['id']}", headers=com_token(fluxo.criador["id"])).json()
    assert atual["situacao"] == "EM_FORMACAO"
    codigos = {
        p["codigo"]
        for i in fluxo.composicao(client, equipe["id"]).json()["integrantes"]
        for p in i["pendencias"]
    }
    assert "COMPROVANTE_NAO_ENVIADO" in codigos  # o vínculo ainda precisa ser comprovado


def test_cadastro_associa_o_convite_a_conta_e_mostra_na_central(client, fluxo, sql):
    equipe, novo, token = fluxo.equipe_com_novato(client)

    criada = fluxo.cadastrar(client, token).json()

    # A conta ainda é pendente e não abre a central pela API; o aviso já está gravado para ela
    convites = sql(
        "SELECT referencia_id FROM notificacoes WHERE usuario_id = :u AND tipo = 'CONVITE'",
        u=criada["id"],
    )
    assert len(convites) == 1
    assert convites[0]["referencia_id"] == fluxo.convite_de(equipe["id"], novo["email"])["id"]


def test_cadastro_com_comprovante_opcional_registra_o_documento(client, fluxo, sql):
    equipe, novo, token = fluxo.equipe_com_novato(client)

    criada = fluxo.cadastrar(client, token, comprovante_url=COMPROVANTE).json()

    [comprovante] = fluxo.sql(
        "SELECT * FROM comprovantes_vinculo WHERE usuario_id = :u", u=criada["id"]
    )
    assert comprovante["status"] == "PENDENTE" and comprovante["arquivo_url"] == COMPROVANTE
    assert comprovante["hackathon_id"] == fluxo.hackathon_id
    assert comprovante["tipo_vinculo"] == "ESTUDANTE"  # o tipo indicado no convite (padrão)


def test_comprovante_do_cadastro_por_convite_vale_para_o_tipo_indicado_pelo_lider(client, fluxo):
    """BE-S5-03: só vale na homologação o comprovante do tipo que o líder indicou."""
    novo = fluxo.indicado("Paula Profissional")
    equipe = fluxo.criar_ok(
        client, categoria="PROFISSIONAIS", integrantes=[novo, fluxo.indicado("Outra")]
    )
    token = fluxo.token_do_email(novo["email"])

    criada = fluxo.cadastrar(client, token, comprovante_url=COMPROVANTE).json()

    [comprovante] = fluxo.sql(
        "SELECT tipo_vinculo FROM comprovantes_vinculo WHERE usuario_id = :u", u=criada["id"]
    )
    assert comprovante["tipo_vinculo"] == "PROFISSIONAL"
    # Depois de aprovado e de aceitar o convite, o vínculo conta como comprovado na composição
    fluxo.sql(
        "UPDATE comprovantes_vinculo SET status = 'APROVADO', validado_em = now()"
        " WHERE usuario_id = :u",
        u=criada["id"],
    )
    pessoa = {"id": criada["id"], "email": novo["email"]}
    assert fluxo.aceitar_como(client, pessoa, equipe["id"], novo["email"]).status_code == 200
    composicao = fluxo.composicao(client, equipe["id"]).json()
    dela = next(
        i["confirmado_pelo_integrante"]
        for i in composicao["integrantes"]
        if i["confirmado_pelo_integrante"]["usuario_id"] == str(criada["id"])
    )
    assert dela["vinculo_comprovado"] is True


def test_o_link_serve_uma_vez_so(client, fluxo):
    equipe, novo, token = fluxo.equipe_com_novato(client)
    assert fluxo.cadastrar(client, token).status_code == 201

    segundo = fluxo.cadastrar(client, token)
    consulta = fluxo.consultar(client, token)

    assert segundo.status_code == 400 and segundo.json() == INVALIDO
    assert consulta.status_code == 400 and consulta.json() == INVALIDO


# --- Link inválido: sempre a mesma resposta ---


@pytest.mark.parametrize(
    "cenario",
    ["inexistente", "vencido", "cancelado", "equipe-fechada", "inscricoes-encerradas", "recusado"],
)
def test_link_que_nao_vale_mais_da_a_mesma_resposta_400(client, fluxo, cenario):
    equipe, novo, token = fluxo.equipe_com_novato(client)
    convite = fluxo.convite_de(equipe["id"], novo["email"])
    if cenario == "inexistente":
        token = "t" * 43
    elif cenario == "vencido":
        fluxo.sql(
            "UPDATE convites SET token_expira_em = now() - interval '1 minute' WHERE id = :i",
            i=convite["id"],
        )
    elif cenario == "cancelado":
        cancelar = client.post(
            f"/convites/{convite['id']}/cancelar", headers=com_token(fluxo.criador["id"])
        )
        assert cancelar.status_code == 200
    elif cenario == "equipe-fechada":
        fluxo.sql(
            "UPDATE equipes SET situacao = 'AGUARDANDO_HOMOLOGACAO' WHERE id = :e", e=equipe["id"]
        )
    elif cenario == "inscricoes-encerradas":
        fluxo.definir_status("INSCRICOES_ENCERRADAS")
    else:
        fluxo.sql(
            "UPDATE convites SET status = 'RECUSADO', respondido_em = now() WHERE id = :i",
            i=convite["id"],
        )

    consulta = fluxo.consultar(client, token)
    cadastro = fluxo.cadastrar(client, token)

    assert (consulta.status_code, consulta.json()) == (400, INVALIDO)
    assert (cadastro.status_code, cadastro.json()) == (400, INVALIDO)
    assert fluxo.usuario_por_email(novo["email"]) is None


def test_se_ja_existe_conta_com_o_email_do_convite_responde_409(client, fluxo, sql):
    equipe, novo, token = fluxo.equipe_com_novato(client)
    sql(
        "INSERT INTO usuarios (email, papel, senha_hash) VALUES (:e, 'PARTICIPANTE', 'x')",
        e=novo["email"],
    )

    resposta = fluxo.cadastrar(client, token)

    assert resposta.status_code == 409
    assert fluxo.convite_de(equipe["id"], novo["email"])["token_utilizado_em"] is None


# --- Cadastro indevido: 422 e nada é gravado ---


@pytest.mark.parametrize(
    "campos",
    [
        {"senha": "curta1"},
        {"senha": "somenteletras"},
        {"senha": "12345678"},
        {"email": "outro@testes.com"},
        {"papel": "ORGANIZADOR"},
        {"situacao_conta": "ATIVA"},
        {"hackathon_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
        {"comprovante_url": "http://res.cloudinary.com/demo/comprovante.pdf"},
        {"comprovante_url": "https://res.cloudinary.com/demo/comprovante.exe"},
        {"periodo": 0},
        {"nome": "   "},
    ],
    ids=[
        "senha-curta",
        "senha-sem-numero",
        "senha-sem-letra",
        "outro-email",
        "papel",
        "situacao-conta",
        "hackathon",
        "comprovante-http",
        "comprovante-exe",
        "periodo-zero",
        "nome-em-branco",
    ],
)
def test_cadastro_por_convite_invalido_da_422_e_nao_gasta_o_link(client, fluxo, campos):
    equipe, novo, token = fluxo.equipe_com_novato(client)

    resposta = fluxo.cadastrar(client, token, **campos)

    assert resposta.status_code == 422
    assert fluxo.usuario_por_email(novo["email"]) is None
    assert fluxo.convite_de(equipe["id"], novo["email"])["token_utilizado_em"] is None
    assert fluxo.cadastrar(client, token).status_code == 201  # o link continua valendo


def test_token_curto_demais_da_422(client, fluxo):
    assert fluxo.consultar(client, "curto").status_code == 422
    assert fluxo.cadastrar(client, "curto").status_code == 422


def test_dois_cadastros_simultaneos_com_o_mesmo_link_criam_uma_conta(client, fluxo):
    equipe, novo, token = fluxo.equipe_com_novato(client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(fluxo.cadastrar, client, token) for _ in range(2)]
        codigos = sorted(f.result().status_code for f in futuros)

    assert codigos == [201, 400]
    assert (
        fluxo.sql(
            "SELECT count(*) AS n FROM usuarios WHERE lower(email) = lower(:e)", e=novo["email"]
        )[0]["n"]
        == 1
    )


# --- Cadastro público também associa convites pendentes ---


def test_cadastro_publico_associa_convites_pendentes(client, fluxo):
    equipe, novo, _ = fluxo.equipe_com_novato(client)

    resposta = client.post(
        "/auth/cadastro",
        json={
            "hackathon_id": str(fluxo.hackathon_id),
            "nome": "Nina Nova",
            "email": novo["email"],
            "senha": SENHA_NOVA,
            "instituicao": "UFPA",
            "curso": "SI",
            "periodo": 3,
            "comprovante_url": COMPROVANTE,
        },
    )

    assert resposta.status_code == 201, resposta.text
    convite = fluxo.convite_de(equipe["id"], novo["email"])
    assert str(convite["usuario_id"]) == resposta.json()["id"]
    avisos = fluxo.sql(
        "SELECT 1 FROM notificacoes WHERE usuario_id = :u AND tipo = 'CONVITE'",
        u=resposta.json()["id"],
    )
    assert len(avisos) == 1


# --- Conta pendente só responde ao convite ---


def test_conta_pendente_nao_cria_equipe_nem_convida_mas_mentor_sem_ativacao_segue_barrado(
    client, fluxo, usuario_no_banco
):
    pendente = usuario_no_banco(situacao_conta="PENDENTE")
    mentor = usuario_no_banco(papel="MENTOR")

    assert fluxo.criar(client, quem=pendente).status_code == 403
    assert client.get("/convites/meus", headers=com_token(pendente["id"])).status_code == 200
    assert client.get("/convites/meus", headers=com_token(mentor["id"])).status_code == 403
    termos = client.get(
        f"/hackathons/{fluxo.hackathon_id}/termos/vigentes", headers=com_token(mentor["id"])
    )
    assert termos.status_code == 403


# --- Segurança do token ---


def test_o_token_nao_aparece_em_nenhuma_resposta_da_api(client, fluxo):
    equipe, novo, token = fluxo.equipe_com_novato(client)
    convite = fluxo.convite_de(equipe["id"], novo["email"])
    cabecalho = com_token(fluxo.criador["id"])

    respostas = [
        client.get(f"/equipes/{equipe['id']}/convites", headers=cabecalho),
        fluxo.composicao(client, equipe["id"]),
        client.get(f"/equipes/{equipe['id']}/painel", headers=cabecalho),
        client.get(f"/equipes/{equipe['id']}", headers=cabecalho),
        fluxo.consultar(client, token),
    ]

    for resposta in respostas:
        assert resposta.status_code == 200, resposta.text
        assert token not in resposta.text
        assert convite["token_hash"] not in resposta.text
        assert "token" not in resposta.text.lower()


# --- Idempotência do POST /equipes ---


def test_repetir_o_pedido_com_a_mesma_chave_devolve_a_equipe_sem_duplicar(client, fluxo, sql):
    integrantes = [fluxo.indicado("Ana"), fluxo.indicado("Bia")]

    primeira = fluxo.criar_com_chave(client, "pedido-1", integrantes=integrantes)
    antes = len(sql("SELECT 1 FROM emails_outbox WHERE tipo = 'CONVITE_EQUIPE'"))
    segunda = fluxo.criar_com_chave(client, "pedido-1", integrantes=integrantes)

    assert primeira.status_code == 201, primeira.text
    assert segunda.status_code == 200, segunda.text
    assert segunda.json() == primeira.json()
    assert fluxo.equipes_do_criador() == 1
    equipe_id = primeira.json()["id"]
    assert len(sql("SELECT 1 FROM convites WHERE equipe_id = :e", e=equipe_id)) == 2
    assert len(sql("SELECT 1 FROM emails_outbox WHERE tipo = 'CONVITE_EQUIPE'")) == antes


def test_chave_reutilizada_com_outro_conteudo_da_409(client, fluxo):
    assert fluxo.criar_com_chave(client, "pedido-2", nome="Primeira").status_code == 201

    resposta = fluxo.criar_com_chave(client, "pedido-2", nome="Outra")

    assert resposta.status_code == 409
    assert "Idempotency-Key" in resposta.json()["detail"]
    assert fluxo.equipes_do_criador() == 1


def test_o_hash_ignora_maiusculas_nos_emails(client, fluxo):
    email = fluxo.novo_email()
    base = {"integrantes": [{"nome": "Ana", "email": email}, fluxo.indicado("Bia")]}
    primeira = fluxo.criar_com_chave(client, "pedido-3", **base)
    base["integrantes"][0]["email"] = email.upper()

    segunda = fluxo.criar_com_chave(client, "pedido-3", **base)

    assert primeira.status_code == 201 and segunda.status_code == 200


def test_sem_a_chave_o_comportamento_e_o_de_antes(client, fluxo):
    assert fluxo.criar(client).status_code == 201

    assert fluxo.criar(client).status_code == 409


def test_a_chave_vale_por_lider(client, fluxo, usuario_no_banco):
    outro = usuario_no_banco()

    a = fluxo.criar_com_chave(client, "mesma-chave")
    b = fluxo.criar_com_chave(client, "mesma-chave", quem=outro)

    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


@pytest.mark.parametrize("chave", ["", "x" * 129])
def test_chave_vazia_ou_longa_demais_da_422(client, fluxo, chave):
    assert fluxo.criar_com_chave(client, chave).status_code == 422
    assert fluxo.equipes_do_criador() == 0


def test_pedidos_simultaneos_com_a_mesma_chave_geram_uma_equipe(client, fluxo, sql):
    integrantes = [fluxo.indicado(), fluxo.indicado()]

    with ThreadPoolExecutor(max_workers=3) as pool:
        futuros = [
            pool.submit(fluxo.criar_com_chave, client, "corrida", integrantes=integrantes)
            for _ in range(3)
        ]
        respostas = [f.result() for f in futuros]

    assert sorted(r.status_code for r in respostas) == [200, 200, 201]
    assert len({r.json()["id"] for r in respostas}) == 1
    assert fluxo.equipes_do_criador() == 1
    equipe_id = respostas[0].json()["id"]
    assert len(sql("SELECT 1 FROM convites WHERE equipe_id = :e", e=equipe_id)) == 2


def test_falha_na_validacao_nao_consome_a_chave(client, fluxo):
    invalida = fluxo.criar_com_chave(client, "pedido-4", integrantes=[fluxo.indicado()])
    assert invalida.status_code == 422

    valida = fluxo.criar_com_chave(
        client, "pedido-4", integrantes=[fluxo.indicado(), fluxo.indicado()]
    )

    assert valida.status_code == 201, valida.text


# --- OpenAPI e migration ---


def test_swagger_documenta_o_cadastro_por_convite_e_a_chave(client):
    documento = client.get("/openapi.json").json()
    consulta = documento["paths"]["/auth/cadastro/convite/consulta"]["post"]
    cadastro = documento["paths"]["/auth/cadastro/convite"]["post"]
    assert "400" in consulta["responses"]
    assert {"400", "409", "422"} <= set(cadastro["responses"])
    assert "security" not in cadastro and "security" not in consulta  # públicos, sem login
    criar = documento["paths"]["/equipes"]["post"]
    assert "Idempotency-Key" in {p["name"] for p in criar["parameters"]}
    esquemas = documento["components"]["schemas"]
    assert esquemas["CadastroPorConviteRequest"]["additionalProperties"] is False
    assert "papel" not in esquemas["CadastroPorConviteRequest"]["properties"]
    assert "email" not in esquemas["CadastroPorConviteRequest"]["properties"]


def test_migration_token_do_convite_e_idempotencia_da_equipe():
    async def verificar(conn):
        hackathon, usuario = await novo_hackathon(conn), await novo_usuario(conn)
        equipe = await sql_na_transacao(
            conn, "INSERT INTO equipes (hackathon_id) VALUES (:h) RETURNING id", h=hackathon
        )
        inserir = (
            "INSERT INTO convites (equipe_id, nome, email, convidado_por{col})"
            " VALUES (:e, 'N', :m, :u{val})"
        )
        # Token sem validade é barrado; o legado (sem token) continua válido
        with pytest.raises(IntegrityError, match="ck_convites_token"):
            async with conn.begin_nested():
                await sql_na_transacao(
                    conn,
                    inserir.format(col=", token_hash", val=", 'abc'"),
                    e=equipe,
                    m="a@t.com",
                    u=usuario,
                )
        await sql_na_transacao(
            conn, inserir.format(col="", val=""), e=equipe, m="b@t.com", u=usuario
        )
        agora = datetime.now(UTC).replace(tzinfo=None)
        colunas = ", token_hash, token_expira_em"
        valores = ", 'h1', :x"
        await sql_na_transacao(
            conn,
            inserir.format(col=colunas, val=valores),
            e=equipe,
            m="c@t.com",
            u=usuario,
            x=agora,
        )
        with pytest.raises(IntegrityError, match="uq_convites_token_hash"):
            async with conn.begin_nested():
                await sql_na_transacao(
                    conn,
                    inserir.format(col=colunas, val=valores),
                    e=equipe,
                    m="d@t.com",
                    u=usuario,
                    x=agora,
                )
        # Chave sem hash do conteúdo é barrada; a mesma chave do mesmo criador não repete
        with pytest.raises(IntegrityError, match="ck_equipes_idempotencia"):
            async with conn.begin_nested():
                await sql_na_transacao(
                    conn,
                    "INSERT INTO equipes (hackathon_id, criada_por, chave_idempotencia)"
                    " VALUES (:h, :u, 'k')",
                    h=hackathon,
                    u=usuario,
                )
        completa = (
            "INSERT INTO equipes (hackathon_id, criada_por, chave_idempotencia, hash_requisicao)"
            " VALUES (:h, :u, 'k', 'hash')"
        )
        await sql_na_transacao(conn, completa, h=hackathon, u=usuario)
        with pytest.raises(IntegrityError, match="uq_equipes_idempotencia"):
            async with conn.begin_nested():
                await sql_na_transacao(conn, completa, h=hackathon, u=usuario)

    rodar(verificar)
