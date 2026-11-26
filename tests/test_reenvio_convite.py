"""
Reenvio seguro e correção de convite pendente (BE-S5-06; RF01, RF18, RF19, RF20, RF60).

Cobre `POST /convites/{id}/reenviar` e `PATCH /convites/{id}`: token novo que invalida o anterior,
quem pode pedir, estados do convite, intervalo mínimo e máximo de reenvios, aviso antigo retirado
da fila, notificação da conta antiga, revalidações da correção, concorrência e privacidade. No fim,
as verificações de contrato do convite (acesso antecipado, link inválido, pré e pós-cadastro e
credenciais) e a migration V202611261000. Os testes gravam no banco de verdade; a fixture `reenvio`
apaga o que cria (usuários e e-mails saem pelas fixtures de conftest.py).
"""

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.const.config import settings
from tests.helpers_email import emails_de
from tests.test_cadastro_equipe_integrantes import SENHA_NOVA, CenarioFluxo
from tests.test_convites import com_token
from tests.test_migrations import novo_hackathon, novo_usuario, rodar
from tests.test_migrations import sql as sql_na_transacao

INVALIDO = {"detail": "Link de convite inválido, vencido ou já utilizado."}
MAXIMO = settings.CONVITE_REENVIO_MAX
INTERVALO = settings.CONVITE_REENVIO_INTERVALO_SEGUNDOS


class CenarioReenvio(CenarioFluxo):
    def reenviar(self, client, convite_id, quem=None):
        return client.post(
            f"/convites/{convite_id}/reenviar", headers=com_token((quem or self.criador)["id"])
        )

    def corrigir(self, client, convite_id, quem=None, **corpo):
        return client.patch(
            f"/convites/{convite_id}",
            headers=com_token((quem or self.criador)["id"]),
            json=corpo,
        )

    def liberar_intervalo(self, convite_id):
        """Faz de conta que o último aviso saiu há uma hora."""
        self.sql(
            "UPDATE convites SET ultimo_envio_em = now() - interval '1 hour' WHERE id = :i",
            i=convite_id,
        )

    def convidar_avulso(self, client, equipe_id, indicado: dict):
        return client.post(
            f"/equipes/{equipe_id}/convites",
            headers=com_token(self.criador["id"]),
            json=indicado,
        )

    def convite(self, convite_id) -> dict:
        return self.sql("SELECT * FROM convites WHERE id = :i", i=convite_id)[0]

    def pendente(self, client, **extra) -> tuple[dict, dict, dict]:
        """Equipe com dois convidados sem conta. Devolve a equipe, o convite do primeiro (linha
        do banco) e o token do link dele."""
        equipe, novo, token = self.equipe_com_novato(client, **extra)
        return equipe, self.convite_de(equipe["id"], novo["email"]), token

    def valido(self, client, token) -> bool:
        return self.consultar(client, token).status_code == 200

    def tokens_nos_emails(self, *enderecos) -> list[str]:
        """Tokens que ainda existem em corpo de e-mail da fila (cancelados perdem o corpo)."""
        achados = []
        for endereco in enderecos:
            for email in emails_de(self.sql, endereco, "CONVITE_EQUIPE"):
                achado = re.search(r"/cadastro#convite=([\w-]+)", email["corpo_texto"] or "")
                if achado:
                    achados.append(achado.group(1))
        return achados

    def chaves_do_convite(self, usuario_id, convite_id) -> list[str]:
        return [
            n["chave_idempotencia"] for n in self.notificacoes_do_convite(usuario_id, convite_id)
        ]

    def trocar_email(self, client, convite_id) -> int:
        """Corrige o e-mail para um endereço novo e devolve o status da resposta."""
        return self.corrigir(client, convite_id, email=self.novo_email()).status_code

    def notificacoes_do_convite(self, usuario_id, convite_id) -> list[dict]:
        return self.sql(
            "SELECT chave_idempotencia, lida_em FROM notificacoes WHERE usuario_id = :u"
            " AND tipo = 'CONVITE' AND referencia_id = :c ORDER BY chave_idempotencia",
            u=usuario_id,
            c=convite_id,
        )


@pytest.fixture
def reenvio(sql, usuario_no_banco, novo_email):
    cenario = CenarioReenvio(sql, usuario_no_banco, novo_email)
    yield cenario
    cenario.limpar()


# --- Reenvio: token novo, link antigo morto ---


def test_reenvio_gera_token_novo_e_invalida_o_anterior(client, reenvio, sql):
    equipe, convite, antigo = reenvio.pendente(client)
    reenvio.liberar_intervalo(convite["id"])

    resposta = reenvio.reenviar(client, convite["id"])

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["status"] == "PENDENTE" and corpo["reenvios"] == 1
    novo = reenvio.token_do_email(convite["email"])
    assert novo != antigo
    # O link antigo cai no 400 genérico; o novo vale e cadastra
    velho = reenvio.consultar(client, antigo)
    assert (velho.status_code, velho.json()) == (400, INVALIDO)
    assert reenvio.cadastrar(client, antigo).status_code == 400
    assert reenvio.valido(client, novo)
    assert reenvio.cadastrar(client, novo).status_code == 201
    # O banco guarda só o hash do token novo; o valor puro não está na resposta nem na linha
    linha = reenvio.convite(convite["id"])
    assert linha["token_hash"] == hashlib.sha256(novo.encode()).hexdigest()
    assert novo not in resposta.text and antigo not in resposta.text
    assert novo not in {str(v) for v in linha.values()}


def test_reenvio_renova_a_validade_de_um_link_vencido(client, reenvio):
    equipe, convite, antigo = reenvio.pendente(client)
    reenvio.sql(
        "UPDATE convites SET token_expira_em = now() - interval '1 minute',"
        " ultimo_envio_em = now() - interval '1 hour' WHERE id = :i",
        i=convite["id"],
    )
    assert reenvio.consultar(client, antigo).status_code == 400

    assert reenvio.reenviar(client, convite["id"]).status_code == 200

    novo = reenvio.token_do_email(convite["email"])
    consulta = reenvio.consultar(client, novo)
    assert consulta.status_code == 200
    expira = datetime.fromisoformat(consulta.json()["expira_em"]).replace(tzinfo=None)
    assert expira > datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)


def test_o_aviso_novo_usa_a_chave_do_envio_e_retira_o_antigo_da_fila(client, reenvio, sql):
    equipe, convite, _ = reenvio.pendente(client)
    reenvio.liberar_intervalo(convite["id"])
    assert reenvio.reenviar(client, convite["id"]).status_code == 200
    reenvio.liberar_intervalo(convite["id"])
    assert reenvio.reenviar(client, convite["id"]).status_code == 200

    fila = emails_de(sql, convite["email"], "CONVITE_EQUIPE")
    emails = {e["chave_idempotencia"]: e for e in fila}

    assert set(emails) == {
        f"convite:{convite['id']}",
        f"convite:{convite['id']}:envio:1",
        f"convite:{convite['id']}:envio:2",
    }
    # Os avisos que o worker ainda não tinha pego saem da fila, sem corpo (o token antigo some)
    for chave in (f"convite:{convite['id']}", f"convite:{convite['id']}:envio:1"):
        retirado = emails[chave]
        assert retirado["status"] == "FALHA" and retirado["cancelado_em"] is not None
        assert retirado["corpo_texto"] is None and retirado["corpo_html"] is None
    vigente = emails[f"convite:{convite['id']}:envio:2"]
    assert vigente["status"] == "PENDENTE" and vigente["cancelado_em"] is None
    assert "/cadastro#convite=" in vigente["corpo_texto"]


@pytest.mark.parametrize("estado", ["ENVIANDO", "ENVIADO", "FALHA"])
def test_aviso_que_o_worker_ja_pegou_nao_e_cancelado_e_nao_da_erro(client, reenvio, sql, estado):
    equipe, convite, antigo = reenvio.pendente(client)
    reenvio.liberar_intervalo(convite["id"])
    chave = f"convite:{convite['id']}"
    sql(
        "UPDATE emails_outbox SET status = CAST(:s AS status_email),"
        " reservado_ate = CASE WHEN :s = 'ENVIANDO'"
        "   THEN (now() AT TIME ZONE 'utc') + interval '5 minutes' END,"
        " enviado_em = CASE WHEN :s = 'ENVIADO' THEN (now() AT TIME ZONE 'utc') END"
        " WHERE chave_idempotencia = :c",
        s=estado,
        c=chave,
    )

    resposta = reenvio.reenviar(client, convite["id"])

    assert resposta.status_code == 200, resposta.text
    [anterior] = sql("SELECT * FROM emails_outbox WHERE chave_idempotencia = :c", c=chave)
    assert anterior["status"] == estado and anterior["cancelado_em"] is None
    assert anterior["corpo_texto"] is not None
    # O reenvio segue: o aviso novo entra na fila e o link antigo já não vale
    assert not reenvio.valido(client, antigo)
    assert reenvio.valido(client, reenvio.token_do_email(convite["email"]))


def test_dois_links_diferentes_nunca_valem_ao_mesmo_tempo_e_o_400_e_identico(client, reenvio):
    equipe, convite, original = reenvio.pendente(client)
    reenvio.liberar_intervalo(convite["id"])
    assert reenvio.reenviar(client, convite["id"]).status_code == 200
    vigente = reenvio.token_do_email(convite["email"])
    # Vencido: o vigente expira; reutilizado: o vigente é gasto no cadastro
    [outro] = reenvio.sql(
        "SELECT * FROM convites WHERE equipe_id = :e AND id <> :i", e=equipe["id"], i=convite["id"]
    )
    outro_token = reenvio.token_do_email(outro["email"])
    reenvio.sql(
        "UPDATE convites SET token_expira_em = now() - interval '1 minute' WHERE id = :i",
        i=outro["id"],
    )
    reenvio.cadastrar(client, vigente)

    respostas = {
        "substituido": reenvio.consultar(client, original),
        "reutilizado": reenvio.consultar(client, vigente),
        "vencido": reenvio.consultar(client, outro_token),
    }

    assert {(r.status_code, r.content) for r in respostas.values()} == {
        (400, respostas["vencido"].content)
    }
    assert respostas["vencido"].json() == INVALIDO


# --- Reenvio: convidado com conta e conta criada depois ---


def test_reenvio_para_quem_ja_tem_conta_usa_a_central_e_o_email_de_convites(client, reenvio, sql):
    existente, item = reenvio.com_conta()
    equipe = reenvio.criar_ok(client, integrantes=[item, reenvio.indicado()])
    convite = reenvio.convite_de(equipe["id"], existente["email"])
    reenvio.liberar_intervalo(convite["id"])

    resposta = reenvio.reenviar(client, convite["id"])

    assert resposta.status_code == 200, resposta.text
    chaves = reenvio.chaves_do_convite(existente["id"], convite["id"])
    assert chaves == [f"convite:{convite['id']}", f"convite:{convite['id']}:envio:1"]
    emails = emails_de(sql, existente["email"], "CONVITE_EQUIPE")
    assert len(emails) == 2
    novo = next(e for e in emails if e["chave_idempotencia"].endswith(":envio:1"))
    assert "/convites" in novo["corpo_texto"] and "#convite=" not in novo["corpo_texto"]
    linha = reenvio.convite(convite["id"])
    assert linha["token_hash"] is None and linha["usuario_id"] == existente["id"]


def test_convite_pos_cadastro_reenviado_vira_aviso_de_conta_e_mata_o_link(client, reenvio, sql):
    equipe, convite, token = reenvio.pendente(client)
    criada = reenvio.cadastrar(client, token).json()  # a conta já existe; o convite segue pendente
    conta_id = UUID(criada["id"])
    reenvio.liberar_intervalo(convite["id"])

    resposta = reenvio.reenviar(client, convite["id"])

    assert resposta.status_code == 200, resposta.text
    linha = reenvio.convite(convite["id"])
    assert linha["usuario_id"] == conta_id and linha["token_hash"] is None
    chaves = reenvio.chaves_do_convite(conta_id, convite["id"])
    assert chaves == [f"convite:{convite['id']}", f"convite:{convite['id']}:envio:1"]
    novo = emails_de(sql, convite["email"], "CONVITE_EQUIPE")[-1]
    assert "/convites" in novo["corpo_texto"] and "#convite=" not in novo["corpo_texto"]
    assert reenvio.consultar(client, token).json() == INVALIDO


# --- Quem pode pedir e em que estado ---


def test_so_o_lider_reenvia(client, reenvio, usuario_no_banco):
    existente, item = reenvio.com_conta()
    novato = reenvio.indicado()
    equipe = reenvio.criar_ok(client, integrantes=[item, novato])
    outro = reenvio.convite_de(equipe["id"], novato["email"])
    aceite = reenvio.aceitar_como(client, existente, equipe["id"], existente["email"])
    assert aceite.status_code == 200, aceite.text
    reenvio.liberar_intervalo(outro["id"])

    de_fora = reenvio.reenviar(client, outro["id"], quem=usuario_no_banco())
    integrante = reenvio.reenviar(client, outro["id"], quem=existente)
    inexistente = reenvio.reenviar(client, uuid4())
    sem_login = client.post(f"/convites/{outro['id']}/reenviar")

    assert (de_fora.status_code, integrante.status_code) == (404, 403)
    assert inexistente.status_code == 404 and sem_login.status_code == 401
    # Quem é de fora recebe a mesma resposta de um convite que não existe
    assert de_fora.json() == inexistente.json()
    assert reenvio.convite(outro["id"])["reenvios"] == 0
    assert reenvio.reenviar(client, outro["id"]).status_code == 200


def test_dev_tambem_reenvia(client, reenvio, usuario_no_banco):
    equipe, convite, _ = reenvio.pendente(client)
    reenvio.liberar_intervalo(convite["id"])

    dev = usuario_no_banco(papel="DEV")
    assert reenvio.reenviar(client, convite["id"], quem=dev).status_code == 200


def test_conta_pendente_nao_reenvia(client, reenvio, usuario_no_banco):
    equipe, convite, _ = reenvio.pendente(client)
    pendente = usuario_no_banco(situacao_conta="PENDENTE")

    assert reenvio.reenviar(client, convite["id"], quem=pendente).status_code == 403
    assert reenvio.corrigir(client, convite["id"], quem=pendente, nome="X").status_code == 403


@pytest.mark.parametrize(
    "estado", ["aceito", "recusado", "cancelado", "inscricoes-encerradas", "equipe-fechada"]
)
def test_convite_que_nao_pode_mais_ser_renovado_da_409(client, reenvio, estado):
    equipe, convite, _ = reenvio.pendente(client)
    reenvio.liberar_intervalo(convite["id"])
    if estado == "aceito":
        reenvio.sql(
            "UPDATE convites SET status = 'ACEITO', respondido_em = now() WHERE id = :i",
            i=convite["id"],
        )
    elif estado == "recusado":
        reenvio.sql(
            "UPDATE convites SET status = 'RECUSADO', respondido_em = now() WHERE id = :i",
            i=convite["id"],
        )
    elif estado == "cancelado":
        reenvio.sql("UPDATE convites SET status = 'CANCELADO' WHERE id = :i", i=convite["id"])
    elif estado == "inscricoes-encerradas":
        reenvio.definir_status("INSCRICOES_ENCERRADAS")
    else:
        reenvio.sql(
            "UPDATE equipes SET situacao = 'AGUARDANDO_HOMOLOGACAO' WHERE id = :e", e=equipe["id"]
        )

    reenviar = reenvio.reenviar(client, convite["id"])
    corrigir = reenvio.corrigir(client, convite["id"], nome="Outro nome")

    assert (reenviar.status_code, corrigir.status_code) == (409, 409)
    linha = reenvio.convite(convite["id"])
    assert linha["reenvios"] == 0 and linha["nome"] == convite["nome"]


# --- Anti-abuso: intervalo mínimo e máximo ---


def test_reenvio_antes_do_intervalo_da_429_com_retry_after(client, reenvio):
    equipe, convite, _ = reenvio.pendente(client)

    cedo = reenvio.reenviar(client, convite["id"])

    assert cedo.status_code == 429
    assert 1 <= int(cedo.headers["Retry-After"]) <= INTERVALO
    assert reenvio.convite(convite["id"])["reenvios"] == 0
    reenvio.liberar_intervalo(convite["id"])
    assert reenvio.reenviar(client, convite["id"]).status_code == 200
    # O reenvio zera a contagem do intervalo
    assert reenvio.reenviar(client, convite["id"]).status_code == 429
    assert reenvio.convite(convite["id"])["reenvios"] == 1


def test_limite_de_reenvios_da_409_e_zera_o_proximo_reenvio(client, reenvio):
    equipe, convite, _ = reenvio.pendente(client)
    for _ in range(MAXIMO):
        reenvio.liberar_intervalo(convite["id"])
        assert reenvio.reenviar(client, convite["id"]).status_code == 200
    reenvio.liberar_intervalo(convite["id"])

    esgotado = reenvio.reenviar(client, convite["id"])

    assert esgotado.status_code == 409
    assert reenvio.convite(convite["id"])["reenvios"] == MAXIMO
    listados = client.get(
        f"/equipes/{equipe['id']}/convites", headers=com_token(reenvio.criador["id"])
    )
    por_id = {c["id"]: c for c in listados.json()}
    assert por_id[str(convite["id"])]["reenvios"] == MAXIMO
    assert por_id[str(convite["id"])]["proximo_reenvio_em"] is None
    outro = next(c for i, c in por_id.items() if i != str(convite["id"]))
    assert outro["reenvios"] == 0 and outro["proximo_reenvio_em"] is not None


def test_proximo_reenvio_considera_so_o_intervalo(client, reenvio):
    equipe, convite, _ = reenvio.pendente(client)

    resposta = reenvio.reenviar(client, convite["id"])  # cedo demais: 429, nada muda
    assert resposta.status_code == 429
    reenvio.liberar_intervalo(convite["id"])
    antes = datetime.now(UTC)
    corpo = reenvio.reenviar(client, convite["id"]).json()

    proximo = datetime.fromisoformat(corpo["proximo_reenvio_em"])
    assert (
        antes + timedelta(seconds=INTERVALO - 5)
        <= proximo
        <= (datetime.now(UTC) + timedelta(seconds=INTERVALO + 5))
    )
    cancelado = client.post(
        f"/convites/{convite['id']}/cancelar", headers=com_token(reenvio.criador["id"])
    ).json()
    assert cancelado["proximo_reenvio_em"] is None  # só convite pendente pode ser reenviado


# --- Correção de nome e e-mail ---


def test_corrigir_so_o_nome_nao_envia_nada_nem_conta_nos_limites(client, reenvio, sql):
    equipe, convite, token = reenvio.pendente(client)

    resposta = reenvio.corrigir(client, convite["id"], nome="  Nome Corrigido  ")

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["nome"] == "Nome Corrigido" and resposta.json()["reenvios"] == 0
    linha = reenvio.convite(convite["id"])
    assert linha["token_hash"] == convite["token_hash"] and linha["reenvios"] == 0
    assert linha["ultimo_envio_em"] == convite["ultimo_envio_em"]
    assert len(emails_de(sql, convite["email"], "CONVITE_EQUIPE")) == 1
    assert reenvio.valido(client, token)


def test_trocar_o_email_invalida_o_link_antigo_e_avisa_o_endereco_novo(client, reenvio, sql):
    equipe, convite, antigo = reenvio.pendente(client)
    correto = reenvio.novo_email()

    # Sem esperar o intervalo: o convite acabou de ser criado
    resposta = reenvio.corrigir(client, convite["id"], email=correto.upper())

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["email"] == correto and corpo["reenvios"] == 1  # guardado em minúsculas
    assert not reenvio.valido(client, antigo)
    assert reenvio.cadastrar(client, antigo).status_code == 400
    novo = reenvio.token_do_email(correto)
    consulta = reenvio.consultar(client, novo)
    assert consulta.status_code == 200 and consulta.json()["email"] == correto
    linha = reenvio.convite(convite["id"])
    assert linha["token_hash"] == hashlib.sha256(novo.encode()).hexdigest()
    assert novo not in resposta.text and novo not in {str(v) for v in linha.values()}
    # O aviso do endereço antigo ainda na fila é retirado: ninguém ali recebe o link
    [do_antigo] = emails_de(sql, convite["email"], "CONVITE_EQUIPE")
    assert do_antigo["status"] == "FALHA" and do_antigo["corpo_texto"] is None
    # A conta nasce com o e-mail novo e a própria senha; o e-mail antigo continua sem conta
    assert reenvio.cadastrar(client, novo).status_code == 201
    assert reenvio.usuario_por_email(convite["email"]) is None


def test_trocar_o_email_para_quem_ja_tem_conta_liga_o_convite_a_ela(client, reenvio, sql):
    equipe, convite, antigo = reenvio.pendente(client)
    existente = reenvio.usuario_no_banco()
    contas_antes = sql("SELECT count(*) AS n FROM usuarios")[0]["n"]

    resposta = reenvio.corrigir(client, convite["id"], email=existente["email"])

    assert resposta.status_code == 200, resposta.text
    linha = reenvio.convite(convite["id"])
    assert linha["usuario_id"] == existente["id"] and linha["token_hash"] is None
    chaves = reenvio.chaves_do_convite(existente["id"], convite["id"])
    assert chaves == [f"convite:{convite['id']}:envio:1"]
    [aviso] = emails_de(sql, existente["email"], "CONVITE_EQUIPE")
    assert "/convites" in aviso["corpo_texto"] and "#convite=" not in aviso["corpo_texto"]
    assert not reenvio.valido(client, antigo)
    # Nenhuma conta foi criada nem alterada
    assert sql("SELECT count(*) AS n FROM usuarios")[0]["n"] == contas_antes
    conta = sql("SELECT email FROM usuarios WHERE id = :u", u=existente["id"])[0]
    assert conta["email"] == existente["email"]


def test_trocar_o_email_de_quem_tem_conta_marca_o_aviso_antigo_como_lido(client, reenvio):
    antiga, item = reenvio.com_conta()
    equipe = reenvio.criar_ok(client, integrantes=[item, reenvio.indicado()])
    convite = reenvio.convite_de(equipe["id"], antiga["email"])
    avisos = reenvio.notificacoes_do_convite(antiga["id"], convite["id"])
    assert [n["lida_em"] for n in avisos] == [None]
    correto = reenvio.novo_email()

    resposta = reenvio.corrigir(client, convite["id"], email=correto)

    assert resposta.status_code == 200, resposta.text
    avisos = reenvio.notificacoes_do_convite(antiga["id"], convite["id"])
    assert avisos and all(n["lida_em"] is not None for n in avisos)
    linha = reenvio.convite(convite["id"])
    assert linha["usuario_id"] is None and linha["token_hash"] is not None
    assert reenvio.valido(client, reenvio.token_do_email(correto))
    # A conta antiga já não responde a este convite (o convite não é mais dela)
    recusar = client.post(f"/convites/{convite['id']}/recusar", headers=com_token(antiga["id"]))
    assert recusar.status_code == 404


def test_a_troca_de_email_conta_no_limite_sem_esperar_o_intervalo(client, reenvio):
    equipe, convite, _ = reenvio.pendente(client)

    for _ in range(MAXIMO):
        assert reenvio.trocar_email(client, convite["id"]) == 200
    sexta = reenvio.trocar_email(client, convite["id"])

    assert sexta == 409
    assert reenvio.convite(convite["id"])["reenvios"] == MAXIMO
    # Esgotado, nem o reenvio simples (com o intervalo livre) passa; só o nome ainda corrige
    reenvio.liberar_intervalo(convite["id"])
    assert reenvio.reenviar(client, convite["id"]).status_code == 409
    assert reenvio.corrigir(client, convite["id"], nome="Só o nome").status_code == 200


def test_o_reenvio_simples_conta_o_que_a_troca_de_email_ja_gastou(client, reenvio):
    equipe, convite, _ = reenvio.pendente(client)
    for _ in range(MAXIMO - 1):
        assert reenvio.trocar_email(client, convite["id"]) == 200
    # A troca não depende do intervalo, mas o reenvio simples depende
    assert reenvio.reenviar(client, convite["id"]).status_code == 429
    reenvio.liberar_intervalo(convite["id"])
    assert reenvio.reenviar(client, convite["id"]).status_code == 200
    assert reenvio.trocar_email(client, convite["id"]) == 409


# --- Correção: revalidações e formato ---


def test_correcao_nao_aceita_email_repetido_integrante_nem_lider(client, reenvio):
    existente, item = reenvio.com_conta()
    pendente = reenvio.indicado()
    equipe = reenvio.criar_ok(client, integrantes=[item, pendente])
    aceite = reenvio.aceitar_como(client, existente, equipe["id"], existente["email"])
    assert aceite.status_code == 200, aceite.text
    segundo = reenvio.indicado()
    assert reenvio.convidar_avulso(client, equipe["id"], segundo).status_code == 201
    do_segundo = reenvio.convite_de(equipe["id"], segundo["email"])

    repetido = reenvio.corrigir(client, do_segundo["id"], email=pendente["email"])
    integrante = reenvio.corrigir(client, do_segundo["id"], email=existente["email"])
    lider = reenvio.corrigir(client, do_segundo["id"], email=reenvio.criador["email"])

    assert (repetido.status_code, integrante.status_code, lider.status_code) == (409, 409, 409)
    # O 409 não revela e-mail de ninguém além do que o líder já digitou
    for resposta, outro in ((repetido, pendente["email"]), (integrante, existente["email"])):
        assert outro not in resposta.text
    linha = reenvio.convite(do_segundo["id"])
    assert linha["email"] == segundo["email"] and linha["reenvios"] == 0
    assert reenvio.valido(client, reenvio.token_do_email(segundo["email"]))


def test_correcao_respeita_o_maximo_de_integrantes(client, reenvio):
    equipe, convite, _ = reenvio.pendente(client)
    # Lista cheia: líder e dois convidados contam três vagas; a edição passa a aceitar dois
    reenvio.configurar_edicao(min_integrantes=1, max_integrantes=2)

    resposta = reenvio.corrigir(client, convite["id"], email=reenvio.novo_email())

    assert resposta.status_code == 409
    assert reenvio.convite(convite["id"])["email"] == convite["email"]
    # Dentro do limite a correção volta a valer
    reenvio.configurar_edicao(min_integrantes=1, max_integrantes=5)
    assert reenvio.trocar_email(client, convite["id"]) == 200


@pytest.mark.parametrize(
    "corpo",
    [{}, {"nome": ""}, {"email": "nao-e-email"}, {"status": "ACEITO"}, {"nome": "X", "tipo": "Y"}],
)
def test_corpo_invalido_da_422(client, reenvio, corpo):
    equipe, convite, _ = reenvio.pendente(client)

    assert reenvio.corrigir(client, convite["id"], **corpo).status_code == 422
    assert reenvio.convite(convite["id"])["reenvios"] == 0


def test_so_o_lider_corrige(client, reenvio, usuario_no_banco):
    equipe, convite, _ = reenvio.pendente(client)

    de_fora = reenvio.corrigir(client, convite["id"], quem=usuario_no_banco(), nome="X")
    inexistente = reenvio.corrigir(client, uuid4(), nome="X")
    sem_login = client.patch(f"/convites/{convite['id']}", json={"nome": "X"})

    assert de_fora.status_code == 404 and de_fora.json() == inexistente.json()
    assert sem_login.status_code == 401
    assert reenvio.convite(convite["id"])["nome"] == convite["nome"]


# --- Concorrência ---


def test_dois_reenvios_simultaneos_geram_um_unico_token_valido(client, reenvio):
    equipe, convite, antigo = reenvio.pendente(client)
    reenvio.liberar_intervalo(convite["id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(reenvio.reenviar, client, convite["id"]) for _ in range(2)]
        codigos = sorted(f.result().status_code for f in futuros)

    assert codigos == [200, 429]
    assert reenvio.convite(convite["id"])["reenvios"] == 1
    tokens = reenvio.tokens_nos_emails(convite["email"])
    assert [t for t in tokens if reenvio.valido(client, t)] == tokens and len(tokens) == 1
    assert not reenvio.valido(client, antigo)


def test_troca_de_email_e_reenvio_simultaneos_deixam_um_so_token_valido(client, reenvio):
    equipe, convite, antigo = reenvio.pendente(client)
    reenvio.liberar_intervalo(convite["id"])
    correto = reenvio.novo_email()

    with ThreadPoolExecutor(max_workers=2) as pool:
        corrigir = pool.submit(reenvio.corrigir, client, convite["id"], None, email=correto)
        reenviar = pool.submit(reenvio.reenviar, client, convite["id"])
        resultados = (corrigir.result().status_code, reenviar.result().status_code)

    # A troca nunca espera intervalo; o reenvio ou passa antes dela ou vê o aviso recém-enviado
    assert resultados in {(200, 200), (200, 429)}
    linha = reenvio.convite(convite["id"])
    assert linha["email"] == correto and linha["reenvios"] == resultados.count(200)
    tokens = reenvio.tokens_nos_emails(convite["email"], correto)
    validos = [t for t in tokens if reenvio.valido(client, t)]
    assert len(validos) == 1 and not reenvio.valido(client, antigo)
    assert linha["token_hash"] == hashlib.sha256(validos[0].encode()).hexdigest()


def test_duas_trocas_de_email_simultaneas_deixam_um_so_token_valido(client, reenvio):
    equipe, convite, _ = reenvio.pendente(client)
    emails = [reenvio.novo_email(), reenvio.novo_email()]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [
            pool.submit(reenvio.corrigir, client, convite["id"], None, email=e) for e in emails
        ]
        assert [f.result().status_code for f in futuros] == [200, 200]

    linha = reenvio.convite(convite["id"])
    assert linha["email"] in emails and linha["reenvios"] == 2
    tokens = reenvio.tokens_nos_emails(*emails)
    assert len([t for t in tokens if reenvio.valido(client, t)]) == 1


# --- Privacidade ---


def test_resposta_e_log_nao_vazam_token_nem_email_de_terceiros(client, reenvio, caplog):
    equipe, convite, antigo = reenvio.pendente(client)
    outro_convite = reenvio.sql(
        "SELECT email FROM convites WHERE equipe_id = :e AND id <> :i",
        e=equipe["id"],
        i=convite["id"],
    )[0]
    correto = reenvio.novo_email()
    caplog.set_level(logging.DEBUG)

    resposta = reenvio.corrigir(client, convite["id"], email=correto)
    reenvio.liberar_intervalo(convite["id"])
    reenviado = reenvio.reenviar(client, convite["id"])

    novo = reenvio.token_do_email(correto)
    for texto in (resposta.text, reenviado.text, caplog.text):
        assert novo not in texto and antigo not in texto
        assert outro_convite["email"] not in texto
    assert set(resposta.json()) == {
        "equipe_id",
        "convidado_por",
        "nome",
        "email",
        "id",
        "usuario_id",
        "tipo_integrante",
        "status",
        "enviado_em",
        "respondido_em",
        "reenvios",
        "proximo_reenvio_em",
    }


def test_swagger_documenta_reenvio_e_correcao(client):
    esquema = client.get("/openapi.json").json()
    reenviar = esquema["paths"]["/convites/{convite_id}/reenviar"]["post"]
    corrigir = esquema["paths"]["/convites/{convite_id}"]["patch"]

    assert {"401", "403", "404", "409", "429"} <= set(reenviar["responses"])
    assert {"401", "403", "404", "409", "422"} <= set(corrigir["responses"])
    resposta = esquema["components"]["schemas"]["ConviteResponse"]["properties"]
    assert {"reenvios", "proximo_reenvio_em"} <= set(resposta)
    assert esquema["components"]["schemas"]["ConviteCorrecao"]["additionalProperties"] is False


# --- Verificações do contrato do convite (BE-S5-06) ---


def test_convite_posterior_nao_da_acesso_antecipado_a_equipe_em_formacao(client, reenvio, sql):
    """Líder recém-criado, equipe EM_FORMACAO, convite criado depois: sem aceitar, a pessoa não é
    integrante e não ganha permissão na equipe, nem com conta, nem depois de reenvio ou correção."""
    equipe = reenvio.criar_ok(client, integrantes=[reenvio.indicado(), reenvio.indicado()])
    convidado = reenvio.usuario_no_banco()
    avulso = reenvio.convidar_avulso(
        client, equipe["id"], {"nome": "Convidado Tardio", "email": convidado["email"]}
    )
    assert avulso.status_code == 201, avulso.text
    convite = avulso.json()
    reenvio.liberar_intervalo(convite["id"])

    assert reenvio.reenviar(client, convite["id"]).status_code == 200

    [linha] = sql("SELECT situacao FROM equipes WHERE id = :e", e=equipe["id"])
    assert linha["situacao"] == "EM_FORMACAO"
    assert reenvio.membros(equipe["id"]).keys().isdisjoint({convidado["id"]})
    assert (
        client.get(
            f"/equipes/{equipe['id']}/convites", headers=com_token(convidado["id"])
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/convites/{convite['id']}/cancelar", headers=com_token(convidado["id"])
        ).status_code
        == 403
    )
    # Nem o convite que recebeu ele consegue reenviar ou corrigir
    assert reenvio.reenviar(client, convite["id"], quem=convidado).status_code == 404
    # Só ao aceitar ele entra
    aceite = reenvio.aceitar_como(client, convidado, equipe["id"], convidado["email"])
    assert aceite.status_code == 200
    assert convidado["id"] in reenvio.membros(equipe["id"])


def test_o_convidado_define_a_propria_senha_e_ninguem_recebe_credenciais(client, reenvio, sql):
    equipe, convite, _ = reenvio.pendente(client)
    correto = reenvio.novo_email()
    assert reenvio.corrigir(client, convite["id"], email=correto).status_code == 200
    reenvio.liberar_intervalo(convite["id"])
    assert reenvio.reenviar(client, convite["id"]).status_code == 200
    novo = reenvio.token_do_email(correto)

    # O líder não criou conta nem senha; sem senha o cadastro nem começa
    assert reenvio.usuario_por_email(correto) is None
    assert reenvio.cadastrar(client, novo, senha=None).status_code == 422
    for email in emails_de(sql, correto, "CONVITE_EQUIPE"):
        assert "senha" not in (email["corpo_texto"] or "").lower().replace("própria senha", "")
    criada = reenvio.cadastrar(client, novo)
    assert criada.status_code == 201 and "senha" not in criada.text.lower()
    login = client.post("/auth/login", json={"email": correto, "senha": SENHA_NOVA})
    assert login.status_code == 200


# --- Migration V202611261000 ---


def test_migration_do_reenvio_de_convites():
    async def verificar(conn):
        historico = await sql_na_transacao(
            conn, "SELECT success FROM flyway_schema_history WHERE version = '202611261000'"
        )
        assert historico is True
        colunas = {
            c: (tipo, padrao)
            for c, tipo, padrao in (
                await conn.execute(
                    text(
                        "SELECT column_name, data_type, column_default"
                        " FROM information_schema.columns WHERE table_name = 'convites'"
                        " AND column_name IN ('reenvios', 'ultimo_envio_em')"
                    )
                )
            ).all()
        }
        assert colunas["ultimo_envio_em"][0] == "timestamp with time zone"
        assert colunas["reenvios"][0] == "smallint" and colunas["reenvios"][1] == "0"
        hackathon, usuario = await novo_hackathon(conn), await novo_usuario(conn)
        equipe = await sql_na_transacao(
            conn, "INSERT INTO equipes (hackathon_id) VALUES (:h) RETURNING id", h=hackathon
        )
        # Convite novo nasce com 0 reenvios e o último envio em "agora" (UTC, com fuso)
        convite = await sql_na_transacao(
            conn,
            "INSERT INTO convites (equipe_id, nome, email, convidado_por)"
            " VALUES (:e, 'N', 'a@t.com', :u) RETURNING id",
            e=equipe,
            u=usuario,
        )
        linha = (
            await conn.execute(
                text(
                    "SELECT reenvios, ultimo_envio_em IS NOT NULL AS tem,"
                    " abs(extract(epoch FROM (now() - ultimo_envio_em))) < 5 AS agora"
                    " FROM convites WHERE id = :i"
                ),
                {"i": convite},
            )
        ).one()
        assert tuple(linha) == (0, True, True)
        with pytest.raises(IntegrityError, match="ck_convites_reenvios"):
            async with conn.begin_nested():
                await sql_na_transacao(
                    conn, "UPDATE convites SET reenvios = -1 WHERE id = :i", i=convite
                )

    rodar(verificar)
