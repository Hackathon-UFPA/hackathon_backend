"""
Equipes por categoria e composição informada pelo líder (BE-S5-01).

Cobre estudantes, profissionais e mistos, limites, conflitos, unicidade por edição, permissões,
concorrência e compatibilidade com dados legados. Os testes gravam no banco de verdade; a fixture
`cat` apaga o que cria (os usuários e e-mails saem pelas fixtures de conftest.py).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.exc import IntegrityError

from tests.test_convites import Cenario, com_token
from tests.test_migrations import novo_hackathon, novo_usuario, rodar
from tests.test_migrations import sql as sql_na_transacao


class CenarioCategoria(Cenario):
    """Edição em inscrições (3 a 5 integrantes, as três categorias liberadas) com termos
    vigentes. `criador` é quem monta a equipe nova; `lider` (do Cenario) já lidera outra equipe
    desta edição, o que serve aos testes de unicidade."""

    def __init__(self, sql, usuario_no_banco, novo_email):
        super().__init__(sql, usuario_no_banco, novo_email)
        self.criador = usuario_no_banco()

    def indicado(self, nome: str = "Pessoa", tipo: str | None = None, email: str | None = None):
        corpo = {"nome": nome, "email": email or self.novo_email()}
        if tipo is not None:
            corpo["tipo_integrante"] = tipo
        return corpo

    def com_conta(self, tipo: str | None = None, nome: str = "Convidado") -> tuple[dict, dict]:
        """Uma pessoa que já tem conta, e o item de `integrantes` que a indica."""
        usuario = self.usuario_no_banco()
        return usuario, self.indicado(nome, tipo, usuario["email"])

    def criar(self, client, quem=None, **campos):
        return client.post(
            "/equipes",
            headers=com_token((quem or self.criador)["id"]),
            json={"hackathon_id": str(self.hackathon_id), **campos},
        )

    def criar_ok(self, client, **campos) -> dict:
        resposta = self.criar(client, **campos)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    def composicao(self, client, equipe_id, quem=None):
        return client.get(
            f"/equipes/{equipe_id}/composicao", headers=com_token((quem or self.criador)["id"])
        )

    def substituir(self, client, equipe_id, quem=None, **corpo):
        return client.put(
            f"/equipes/{equipe_id}/composicao",
            headers=com_token((quem or self.criador)["id"]),
            json=corpo,
        )

    def convite_de(self, equipe_id, email: str) -> dict:
        [convite] = self.sql(
            "SELECT * FROM convites WHERE equipe_id = :e AND lower(email) = lower(:m)"
            " ORDER BY enviado_em DESC LIMIT 1",
            e=equipe_id,
            m=email,
        )
        return convite

    def membros(self, equipe_id) -> dict:
        linhas = self.sql(
            "SELECT usuario_id, funcao, tipo_integrante FROM membros_equipe WHERE equipe_id = :e",
            e=equipe_id,
        )
        return {linha["usuario_id"]: linha for linha in linhas}

    def aceitar_como(self, client, usuario: dict, equipe_id, email: str, **extra):
        convite = self.convite_de(equipe_id, email)
        return client.post(
            f"/convites/{convite['id']}/aceitar",
            json={"termos_ids": self.termos_ids, **extra},
            headers=com_token(usuario["id"]),
        )

    def configurar_edicao(self, **campos):
        atribuicoes = ", ".join(f"{campo} = :{campo}" for campo in campos)
        self.sql(f"UPDATE hackathon SET {atribuicoes} WHERE id = :h", h=self.hackathon_id, **campos)

    def sem_nada_gravado(self, quem=None) -> bool:
        usuario = (quem or self.criador)["id"]
        return (
            self.sql("SELECT count(*) AS n FROM membros_equipe WHERE usuario_id = :u", u=usuario)[
                0
            ]["n"]
            == 0
            and self.sql(
                "SELECT count(*) AS n FROM equipes e WHERE e.hackathon_id = :h AND e.id <> :outra",
                h=self.hackathon_id,
                outra=self.equipe_id,
            )[0]["n"]
            == 0
        )


@pytest.fixture
def cat(sql, usuario_no_banco, novo_email):
    cenario = CenarioCategoria(sql, usuario_no_banco, novo_email)
    yield cenario
    cenario.limpar()


def codigos(item: dict) -> set[str]:
    return {p["codigo"] for p in item["pendencias"]}


# --- categorias válidas ------------------------------------------------------------------


def test_estudantes_em_uma_operacao_com_pendencias_individuais(client, cat, sql):
    ana, bia = cat.indicado("Ana"), cat.indicado("Bia")
    equipe = cat.criar_ok(client, categoria="ESTUDANTES", integrantes=[ana, bia])

    assert equipe["categoria"] == "ESTUDANTES" and equipe["situacao"] == "EM_FORMACAO"
    membros = cat.membros(equipe["id"])
    assert len(membros) == 1  # só o líder entra de imediato; os outros pelo aceite
    assert membros[cat.criador["id"]]["funcao"] == "LIDER"
    assert membros[cat.criador["id"]]["tipo_integrante"] == "ESTUDANTE"
    convites = sql("SELECT * FROM convites WHERE equipe_id = :e", e=equipe["id"])
    assert {c["email"] for c in convites} == {ana["email"], bia["email"]}
    assert {c["tipo_integrante"] for c in convites} == {"ESTUDANTE"}
    assert {c["status"] for c in convites} == {"PENDENTE"}

    resposta = cat.composicao(client, equipe["id"])
    assert resposta.status_code == 200, resposta.text
    comp = resposta.json()
    assert comp["categoria"] == "ESTUDANTES"
    assert (comp["total_integrantes"], comp["total_indicados"]) == (1, 3)
    assert (comp["minimo_integrantes"], comp["maximo_integrantes"]) == (3, 5)
    assert "EQUIPE_ABAIXO_DO_MINIMO" in {p["codigo"] for p in comp["pendencias_da_equipe"]}

    lider, *convidados = comp["integrantes"]
    assert lider["indicado_pelo_lider"]["funcao"] == "LIDER"
    assert lider["confirmado_pelo_integrante"]["integrante"] is True
    assert {"TERMOS_NAO_ACEITOS", "COMPROVANTE_NAO_ENVIADO"} <= codigos(lider)
    assert len(convidados) == 2
    for convidado in convidados:
        confirmado = convidado["confirmado_pelo_integrante"]
        assert confirmado["integrante"] is False and confirmado["convite"] == "PENDENTE"
        assert confirmado["usuario_id"] is None and confirmado["termos_aceitos"] is False
        assert codigos(convidado) == {"CONVITE_PENDENTE"}
        assert convidado["indicado_pelo_lider"]["tipo_integrante"] == "ESTUDANTE"


def test_profissionais_sem_tipo_usam_o_da_categoria(client, cat, sql):
    equipe = cat.criar_ok(
        client, categoria="PROFISSIONAIS", integrantes=[cat.indicado(), cat.indicado()]
    )

    assert cat.membros(equipe["id"])[cat.criador["id"]]["tipo_integrante"] == "PROFISSIONAL"
    tipos = sql("SELECT tipo_integrante FROM convites WHERE equipe_id = :e", e=equipe["id"])
    assert {t["tipo_integrante"] for t in tipos} == {"PROFISSIONAL"}
    # O vínculo cobrado é o profissional, não a regra antiga de graduando
    lider = cat.composicao(client, equipe["id"]).json()["integrantes"][0]
    [sem_comprovante] = [p for p in lider["pendencias"] if p["codigo"] == "COMPROVANTE_NAO_ENVIADO"]
    assert "profissional" in sem_comprovante["mensagem"]


def test_equipe_mista_com_estudantes_e_profissionais(client, cat, sql):
    equipe = cat.criar_ok(
        client,
        categoria="MISTA",
        tipo_lider="ESTUDANTE",
        integrantes=[cat.indicado(tipo="PROFISSIONAL"), cat.indicado(tipo="ESTUDANTE")],
    )

    assert cat.membros(equipe["id"])[cat.criador["id"]]["tipo_integrante"] == "ESTUDANTE"
    tipos = sql("SELECT tipo_integrante FROM convites WHERE equipe_id = :e", e=equipe["id"])
    assert sorted(t["tipo_integrante"] for t in tipos) == ["ESTUDANTE", "PROFISSIONAL"]
    painel = client.get(f"/equipes/{equipe['id']}/painel", headers=com_token(cat.criador["id"]))
    assert painel.json()["categoria"] == "MISTA"
    assert painel.json()["integrantes"][0]["tipo_integrante"] == "ESTUDANTE"


@pytest.mark.parametrize("convidados", [2, 4])
def test_limites_incluem_o_lider(client, cat, convidados):
    resposta = cat.criar(client, integrantes=[cat.indicado() for _ in range(convidados)])
    assert resposta.status_code == 201, resposta.text


# --- composições inválidas (nada é gravado) -------------------------------------------------


@pytest.mark.parametrize(
    "categoria,tipo_lider,tipos",
    [
        ("MISTA", "ESTUDANTE", ["ESTUDANTE", "ESTUDANTE"]),
        ("MISTA", "PROFISSIONAL", ["PROFISSIONAL", "PROFISSIONAL"]),
        ("MISTA", "ESTUDANTE", [None, "PROFISSIONAL"]),
        ("MISTA", None, ["ESTUDANTE", "PROFISSIONAL"]),
        ("ESTUDANTES", None, ["PROFISSIONAL", None]),
        ("PROFISSIONAIS", "ESTUDANTE", [None, None]),
    ],
    ids=[
        "mista-so-estudantes",
        "mista-so-profissionais",
        "mista-integrante-sem-tipo",
        "mista-lider-sem-tipo",
        "estudantes-com-profissional",
        "profissionais-com-lider-estudante",
    ],
)
def test_categoria_incoerente_com_os_tipos(client, cat, categoria, tipo_lider, tipos):
    integrantes = [cat.indicado(tipo=tipo) for tipo in tipos]
    campos = {"categoria": categoria, "integrantes": integrantes}
    if tipo_lider:
        campos["tipo_lider"] = tipo_lider

    resposta = cat.criar(client, **campos)

    assert resposta.status_code == 422, resposta.text
    assert cat.sem_nada_gravado()
    emails = [i["email"] for i in integrantes]
    assert cat.sql("SELECT 1 FROM convites WHERE email = ANY(:e)", e=emails) == []


@pytest.mark.parametrize("convidados", [0, 1, 5])
def test_total_fora_do_minimo_e_maximo_da_edicao(client, cat, convidados):
    resposta = cat.criar(client, integrantes=[cat.indicado() for _ in range(convidados)])

    assert resposta.status_code == 422
    assert "de 3 a 5" in resposta.json()["detail"]
    assert cat.sem_nada_gravado()


def test_limites_acompanham_a_configuracao_da_edicao(client, cat):
    cat.configurar_edicao(min_integrantes=2, max_integrantes=2)

    assert cat.criar(client, integrantes=[cat.indicado()]).status_code == 201


def test_email_repetido_ou_do_proprio_lider_nao_vale(client, cat):
    repetido = cat.criar(
        client,
        integrantes=[
            cat.indicado(email="repetido@testes.com"),
            cat.indicado(email="REPETIDO@testes.com"),
        ],
    )
    do_lider = cat.criar(
        client,
        integrantes=[
            cat.indicado(email=cat.criador["email"].upper()),
            cat.indicado(),
        ],
    )

    assert repetido.status_code == 422 and "repetido" in repetido.json()["detail"]
    assert do_lider.status_code == 422
    assert cat.sem_nada_gravado()


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("termos_ids", ["3fa85f64-5717-4562-b3fc-2c963f66afa6"]),
        ("aceitou_termos", True),
        ("comprovante_url", "https://exemplo.com/comprovante.pdf"),
        ("usuario_id", "3fa85f64-5717-4562-b3fc-2c963f66afa6"),
    ],
)
def test_lider_nao_aceita_termos_nem_comprovante_em_nome_de_terceiros(client, cat, campo, valor):
    """RN05 e RN25: o que o líder indica é só nome, e-mail e tipo; o resto dá 422."""
    pessoa = cat.indicado()
    pessoa[campo] = valor

    resposta = cat.criar(client, integrantes=[pessoa, cat.indicado()])

    assert resposta.status_code == 422
    assert cat.sem_nada_gravado()
    aceites = cat.sql(
        "SELECT count(*) AS n FROM aceites_termos WHERE termo_id IN"
        " (SELECT id FROM termos WHERE hackathon_id = :h)",
        h=cat.hackathon_id,
    )
    assert aceites[0]["n"] == 0


@pytest.mark.parametrize(
    "campos",
    [{"categoria": "ESTAGIARIOS"}, {"tipo_lider": "OUTRO"}, {"situacao": "HOMOLOGADA"}],
)
def test_valores_invalidos_do_corpo(client, cat, campos):
    assert cat.criar(client, **campos).status_code == 422
    assert cat.sem_nada_gravado()


# --- política de elegibilidade por edição ---------------------------------------------------


def test_edicao_que_nao_aceita_a_categoria_responde_422_com_as_aceitas(client, cat):
    cat.configurar_edicao(aceita_equipe_mista=False)

    mista = cat.criar(
        client,
        categoria="MISTA",
        tipo_lider="ESTUDANTE",
        integrantes=[cat.indicado(tipo="PROFISSIONAL"), cat.indicado(tipo="ESTUDANTE")],
    )

    assert mista.status_code == 422
    assert "ESTUDANTES" in mista.json()["detail"] and "MISTA," not in mista.json()["detail"]
    assert cat.sem_nada_gravado()
    # As demais categorias seguem liberadas
    assert cat.criar(client, categoria="PROFISSIONAIS").status_code == 201


def test_categoria_omitida_vale_estudantes_e_respeita_a_politica(client, cat):
    cat.configurar_edicao(aceita_equipe_estudantes=False)

    assert cat.criar(client).status_code == 422
    assert cat.sem_nada_gravado()
    assert cat.criar(client, categoria="PROFISSIONAIS").status_code == 201


def test_organizador_configura_a_politica_e_nao_a_zera(client, cat, usuario_no_banco):
    organizador = usuario_no_banco(papel="ORGANIZADOR")
    url = f"/admin/hackathons/{cat.hackathon_id}"
    cabecalho = com_token(organizador["id"])

    ok = client.patch(url, headers=cabecalho, json={"aceita_equipe_profissionais": False})
    assert ok.status_code == 200, ok.text
    assert ok.json()["aceita_equipe_profissionais"] is False
    assert ok.json()["aceita_equipe_estudantes"] is True

    assert (
        client.patch(url, headers=cabecalho, json={"aceita_equipe_mista": None}).status_code == 422
    )
    zerar = client.patch(
        url,
        headers=cabecalho,
        json={"aceita_equipe_estudantes": False, "aceita_equipe_mista": False},
    )
    assert zerar.status_code == 422
    atual = cat.sql("SELECT * FROM hackathon WHERE id = :h", h=cat.hackathon_id)[0]
    assert atual["aceita_equipe_estudantes"] and atual["aceita_equipe_mista"]


def test_categoria_nao_aceita_vira_pendencia_que_bloqueia_a_conclusao(client, cat):
    equipe = cat.criar_ok(client, categoria="MISTA", tipo_lider="PROFISSIONAL")
    cat.configurar_edicao(aceita_equipe_mista=False)

    painel = client.get(f"/equipes/{equipe['id']}/painel", headers=com_token(cat.criador["id"]))

    bloqueios = {p["codigo"] for p in painel.json()["pendencias"] if p["bloqueia_conclusao"]}
    assert "CATEGORIA_NAO_PERMITIDA" in bloqueios
    assert painel.json()["pode_concluir"] is False


# --- unicidade por edição e aceite do convite -----------------------------------------------


def test_lider_que_ja_esta_em_equipe_da_edicao_nao_cria_outra(client, cat):
    cat.criar_ok(client)

    segunda = cat.criar(client)

    assert segunda.status_code == 409
    assert cat.criar(client, quem=cat.lider).status_code == 409  # já lidera a equipe do cenário


def test_convidado_que_ja_esta_em_outra_equipe_da_edicao_nao_entra(client, cat):
    """RN02. Quem monta a equipe não descobre isso na criação (não revelamos quem já está em
    equipe); o conflito aparece quando a pessoa tenta aceitar."""
    equipe = cat.criar_ok(
        client, integrantes=[cat.indicado(email=cat.lider["email"]), cat.indicado()]
    )

    aceite = cat.aceitar_como(client, cat.lider, equipe["id"], cat.lider["email"])

    assert aceite.status_code == 409
    assert cat.convite_de(equipe["id"], cat.lider["email"])["status"] == "PENDENTE"
    assert cat.lider["id"] not in cat.membros(equipe["id"])
    composicao = cat.composicao(client, equipe["id"]).json()
    assert all(
        i["confirmado_pelo_integrante"]["usuario_id"] is None for i in composicao["integrantes"][1:]
    )


def test_aceite_copia_o_tipo_indicado_e_ignora_escolha_do_convidado(client, cat):
    ana, item = cat.com_conta()
    equipe = cat.criar_ok(client, categoria="PROFISSIONAIS", integrantes=[item, cat.indicado()])

    aceite = cat.aceitar_como(client, ana, equipe["id"], ana["email"], tipo_integrante="ESTUDANTE")

    assert aceite.status_code == 200, aceite.text
    assert cat.membros(equipe["id"])[ana["id"]]["tipo_integrante"] == "PROFISSIONAL"


# --- ninguém aceita em nome de terceiros ----------------------------------------------------


def test_termos_e_comprovantes_continuam_individuais(client, cat, sql):
    ana, item = cat.com_conta(nome="Ana")
    equipe = cat.criar_ok(client, integrantes=[item, cat.indicado()])
    assert cat.aceitar_como(client, ana, equipe["id"], ana["email"]).status_code == 200

    comp = cat.composicao(client, equipe["id"]).json()
    por_conta = {
        i["confirmado_pelo_integrante"]["usuario_id"]: i
        for i in comp["integrantes"]
        if i["confirmado_pelo_integrante"]["integrante"]
    }
    lider, convidada = por_conta[str(cat.criador["id"])], por_conta[str(ana["id"])]
    # Ana aceitou os termos com a própria conta; o líder não aceitou nada por ela nem por ele
    assert convidada["confirmado_pelo_integrante"]["termos_aceitos"] is True
    assert lider["confirmado_pelo_integrante"]["termos_aceitos"] is False
    assert "TERMOS_NAO_ACEITOS" in codigos(lider) and "TERMOS_NAO_ACEITOS" not in codigos(convidada)
    assert "COMPROVANTE_NAO_ENVIADO" in codigos(lider) | codigos(convidada)
    aceites = sql("SELECT usuario_id FROM aceites_termos WHERE usuario_id = :u", u=ana["id"])
    assert len(aceites) == 2  # regulamento e consentimento, ambos dela


def test_lider_nao_aceita_o_convite_nem_os_termos_de_outra_pessoa(client, cat, sql):
    ana, item = cat.com_conta()
    equipe = cat.criar_ok(client, integrantes=[item, cat.indicado()])
    convite = cat.convite_de(equipe["id"], ana["email"])

    como_lider = client.post(
        f"/convites/{convite['id']}/aceitar",
        json={"termos_ids": cat.termos_ids},
        headers=com_token(cat.criador["id"]),
    )
    termos = client.post(
        f"/hackathons/{cat.hackathon_id}/termos/aceites",
        json={"termos_ids": cat.termos_ids, "usuario_id": str(ana["id"])},
        headers=com_token(cat.criador["id"]),
    )

    assert como_lider.status_code == 404  # o convite "não existe" para quem não é o destinatário
    assert cat.convite_de(equipe["id"], ana["email"])["status"] == "PENDENTE"
    assert termos.status_code == 201  # o aceite vale para o líder, e só para ele
    assert sql("SELECT 1 FROM aceites_termos WHERE usuario_id = :u", u=ana["id"]) == []
    assert len(sql("SELECT 1 FROM aceites_termos WHERE usuario_id = :u", u=cat.criador["id"])) == 2


# --- convite avulso e dados legados ---------------------------------------------------------


def test_equipe_criada_como_antes_continua_estudantes(client, cat):
    equipe = cat.criar_ok(client, nome="Como antes")

    assert equipe["categoria"] == "ESTUDANTES"
    assert cat.membros(equipe["id"])[cat.criador["id"]]["tipo_integrante"] == "ESTUDANTE"
    resposta = client.post(
        f"/equipes/{equipe['id']}/convites",
        json={"nome": "Maria", "email": cat.novo_email()},
        headers=com_token(cat.criador["id"]),
    )
    assert resposta.status_code == 201 and resposta.json()["tipo_integrante"] == "ESTUDANTE"


def test_equipe_legada_inserida_sem_categoria_funciona_como_estudantes(client, cat):
    """A equipe do cenário foi criada por SQL, sem as colunas novas, como as de antes da tarefa."""
    assert cat.convidar(client).status_code == 201
    convite = cat.sql("SELECT tipo_integrante FROM convites WHERE equipe_id = :e", e=cat.equipe_id)
    assert [c["tipo_integrante"] for c in convite] == ["ESTUDANTE"]
    equipe = client.get(f"/equipes/{cat.equipe_id}", headers=com_token(cat.lider["id"])).json()
    assert equipe["categoria"] == "ESTUDANTES"
    assert cat.membros(cat.equipe_id)[cat.lider["id"]]["tipo_integrante"] == "ESTUDANTE"
    assert cat.composicao(client, cat.equipe_id, cat.lider).status_code == 200


def test_convite_avulso_segue_a_categoria(client, cat):
    estudantes = cat.criar_ok(client)
    url = f"/equipes/{estudantes['id']}/convites"
    cabecalho = com_token(cat.criador["id"])

    incompativel = client.post(
        url,
        json={"nome": "P", "email": cat.novo_email(), "tipo_integrante": "PROFISSIONAL"},
        headers=cabecalho,
    )
    assert incompativel.status_code == 422

    outro = cat.usuario_no_banco()
    mista = cat.criar_ok(client, quem=outro, categoria="MISTA", tipo_lider="ESTUDANTE")
    url_mista = f"/equipes/{mista['id']}/convites"
    cabecalho_mista = com_token(outro["id"])
    sem_tipo = client.post(
        url_mista, json={"nome": "P", "email": cat.novo_email()}, headers=cabecalho_mista
    )
    com_tipo = client.post(
        url_mista,
        json={"nome": "P", "email": cat.novo_email(), "tipo_integrante": "PROFISSIONAL"},
        headers=cabecalho_mista,
    )
    assert sem_tipo.status_code == 422
    assert com_tipo.status_code == 201 and com_tipo.json()["tipo_integrante"] == "PROFISSIONAL"


def test_composicao_incoerente_barra_a_conclusao_e_aparece_no_painel(client, cat, sql):
    equipe = cat.criar_ok(client)  # ESTUDANTES
    sql(
        "UPDATE membros_equipe SET tipo_integrante = 'PROFISSIONAL' WHERE equipe_id = :e",
        e=equipe["id"],
    )

    painel = client.get(f"/equipes/{equipe['id']}/painel", headers=com_token(cat.criador["id"]))

    pendencias = {p["codigo"]: p for p in painel.json()["pendencias"]}
    assert pendencias["CATEGORIA_INCOERENTE"]["bloqueia_conclusao"] is True
    assert painel.json()["pode_concluir"] is False
    conclusao = client.post(
        f"/equipes/{equipe['id']}/inscricao/concluir", headers=com_token(cat.criador["id"])
    )
    assert conclusao.status_code == 409


# --- substituir a composição (RF24) ---------------------------------------------------------


def monta_equipe_com_ana_aceita(client, cat):
    ana, item_ana = cat.com_conta(nome="Ana")
    bia = cat.indicado("Bia")
    equipe = cat.criar_ok(client, integrantes=[item_ana, bia])
    assert cat.aceitar_como(client, ana, equipe["id"], ana["email"]).status_code == 200
    return equipe, ana, item_ana, bia


def test_substituir_adiciona_cancela_e_mantem_quem_ja_entrou(client, cat):
    equipe, ana, item_ana, bia = monta_equipe_com_ana_aceita(client, cat)
    carla = cat.indicado("Carla")

    resposta = cat.substituir(
        client, equipe["id"], categoria="ESTUDANTES", integrantes=[item_ana, carla]
    )

    assert resposta.status_code == 200, resposta.text
    assert cat.convite_de(equipe["id"], bia["email"])["status"] == "CANCELADO"
    assert cat.convite_de(equipe["id"], carla["email"])["status"] == "PENDENTE"
    assert ana["id"] in cat.membros(equipe["id"])
    comp = resposta.json()
    assert (comp["total_integrantes"], comp["total_indicados"]) == (2, 3)
    emails = {i["indicado_pelo_lider"]["email"] for i in comp["integrantes"]}
    assert emails == {cat.criador["email"], ana["email"], carla["email"]}


def test_substituir_remove_avisa_e_nao_deixa_reconvidar_a_mesma_equipe(client, cat):
    equipe, ana, item_ana, bia = monta_equipe_com_ana_aceita(client, cat)
    carla, dani = cat.indicado("Carla"), cat.indicado("Dani")

    resposta = cat.substituir(
        client, equipe["id"], categoria="ESTUDANTES", integrantes=[carla, dani]
    )

    assert resposta.status_code == 200, resposta.text
    assert ana["id"] not in cat.membros(equipe["id"])
    # RF24: quem foi retirado é avisado na central de notificações
    avisos = client.get("/me/notificacoes", headers=com_token(ana["id"])).json()
    removido = [a for a in avisos if (a["dados"] or {}).get("evento") == "REMOVIDO"]
    assert len(removido) == 1 and removido[0]["referencia"]["id"] == equipe["id"]
    # O convite aceito fica no histórico e ainda impede reconvidar (decisão pendente da equipe)
    de_volta = cat.substituir(
        client, equipe["id"], categoria="ESTUDANTES", integrantes=[item_ana, carla]
    )
    assert de_volta.status_code == 409
    assert ana["id"] not in cat.membros(equipe["id"])


def test_substituir_muda_categoria_e_tipos_na_mesma_operacao(client, cat):
    equipe, ana, item_ana, bia = monta_equipe_com_ana_aceita(client, cat)

    resposta = cat.substituir(
        client,
        equipe["id"],
        categoria="MISTA",
        tipo_lider="PROFISSIONAL",
        integrantes=[
            {**item_ana, "tipo_integrante": "ESTUDANTE"},
            {**bia, "tipo_integrante": "PROFISSIONAL"},
        ],
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["categoria"] == "MISTA"
    membros = cat.membros(equipe["id"])
    assert membros[cat.criador["id"]]["tipo_integrante"] == "PROFISSIONAL"
    assert membros[ana["id"]]["tipo_integrante"] == "ESTUDANTE"
    assert cat.convite_de(equipe["id"], bia["email"])["tipo_integrante"] == "PROFISSIONAL"


@pytest.mark.parametrize(
    "corpo",
    [
        {"categoria": "MISTA", "integrantes": []},
        {"categoria": "ESTUDANTES", "integrantes": []},
        {"categoria": "MISTA", "tipo_lider": "ESTUDANTE", "integrantes": "dois"},
    ],
)
def test_substituir_invalido_nao_altera_nada(client, cat, corpo):
    equipe, ana, item_ana, bia = monta_equipe_com_ana_aceita(client, cat)

    assert cat.substituir(client, equipe["id"], **corpo).status_code == 422
    assert ana["id"] in cat.membros(equipe["id"])
    assert cat.convite_de(equipe["id"], bia["email"])["status"] == "PENDENTE"
    assert (
        client.get(f"/equipes/{equipe['id']}", headers=com_token(cat.criador["id"])).json()[
            "categoria"
        ]
        == "ESTUDANTES"
    )


def test_substituir_exige_lider_equipe_em_formacao_e_inscricoes_abertas(
    client, cat, usuario_no_banco, sql
):
    equipe, ana, item_ana, bia = monta_equipe_com_ana_aceita(client, cat)
    corpo = {"categoria": "ESTUDANTES", "integrantes": [item_ana, bia]}
    intruso = usuario_no_banco()

    assert cat.substituir(client, equipe["id"], quem=ana, **corpo).status_code == 403
    assert cat.substituir(client, equipe["id"], quem=intruso, **corpo).status_code == 403
    sem_token = client.put(f"/equipes/{equipe['id']}/composicao", json=corpo)
    assert sem_token.status_code == 401
    inexistente = cat.substituir(client, "3fa85f64-5717-4562-b3fc-2c963f66afa6", **corpo)
    assert inexistente.status_code == 404

    cat.definir_status("INSCRICOES_ENCERRADAS")
    assert cat.substituir(client, equipe["id"], **corpo).status_code == 409
    cat.definir_status("INSCRICOES")
    sql("UPDATE equipes SET situacao = 'AGUARDANDO_HOMOLOGACAO' WHERE id = :e", e=equipe["id"])
    assert cat.substituir(client, equipe["id"], **corpo).status_code == 409
    sql("UPDATE equipes SET situacao = 'EM_FORMACAO' WHERE id = :e", e=equipe["id"])
    assert cat.substituir(client, equipe["id"], **corpo).status_code == 200


def test_dev_substitui_a_composicao_e_os_convites_saem_em_nome_do_lider(
    client, cat, usuario_no_banco
):
    dev = usuario_no_banco(papel="DEV")
    equipe = cat.criar_ok(client, integrantes=[cat.indicado(), cat.indicado()])
    novos = [cat.indicado("Nova"), cat.indicado("Outra")]

    resposta = cat.substituir(
        client, equipe["id"], quem=dev, categoria="ESTUDANTES", integrantes=novos
    )

    assert resposta.status_code == 200, resposta.text
    assert cat.convite_de(equipe["id"], novos[0]["email"])["convidado_por"] == cat.criador["id"]


def test_consultar_composicao_so_para_integrantes(client, cat, usuario_no_banco):
    equipe = cat.criar_ok(client)
    intruso = usuario_no_banco()
    dev = usuario_no_banco(papel="DEV")

    assert cat.composicao(client, equipe["id"], intruso).status_code == 403
    assert cat.composicao(client, equipe["id"], dev).status_code == 200
    assert cat.composicao(client, "3fa85f64-5717-4562-b3fc-2c963f66afa6").status_code == 404
    sem_token = client.get(f"/equipes/{equipe['id']}/composicao")
    assert sem_token.status_code == 401


def test_substituir_e_aceitar_ao_mesmo_tempo_nao_se_atrapalham(client, cat):
    """A rota que muda a composição e o aceite travam na mesma ordem: nada de deadlock (500).
    O convite retirado ou vira 409 para quem aceita, ou a pessoa entra e é retirada em seguida."""
    ana, item_ana = cat.com_conta(nome="Ana")
    equipe = cat.criar_ok(client, integrantes=[item_ana, cat.indicado()])
    novos = [cat.indicado("Carla"), cat.indicado("Dani")]

    with ThreadPoolExecutor(max_workers=2) as pool:
        aceite = pool.submit(cat.aceitar_como, client, ana, equipe["id"], ana["email"])
        troca = pool.submit(
            cat.substituir, client, equipe["id"], categoria="ESTUDANTES", integrantes=novos
        )
        codigo_aceite, codigo_troca = aceite.result().status_code, troca.result().status_code

    assert codigo_troca == 200
    assert codigo_aceite in (200, 409)
    assert ana["id"] not in cat.membros(equipe["id"])
    assert cat.convite_de(equipe["id"], ana["email"])["status"] in ("ACEITO", "CANCELADO")
    if codigo_aceite == 409:
        assert cat.convite_de(equipe["id"], ana["email"])["status"] == "CANCELADO"


def test_duas_criacoes_simultaneas_do_mesmo_lider_geram_uma_equipe(client, cat):
    corpo = {"integrantes": [cat.indicado(), cat.indicado()]}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(cat.criar, client, **corpo) for _ in range(2)]
        codigos_http = sorted(f.result().status_code for f in futuros)

    assert codigos_http == [201, 409]
    assert (
        cat.sql(
            "SELECT count(*) AS n FROM membros_equipe WHERE usuario_id = :u", u=cat.criador["id"]
        )[0]["n"]
        == 1
    )


# --- OpenAPI e migration --------------------------------------------------------------------


def test_swagger_documenta_a_composicao_e_rejeita_campos_extras(client):
    documento = client.get("/openapi.json").json()
    for metodo in ("get", "put"):
        rota = documento["paths"]["/equipes/{equipe_id}/composicao"][metodo]
        assert rota["tags"] == ["Equipes"] and rota["security"]
        assert {"401", "403", "404"} <= set(rota["responses"])
    assert {"409", "422"} <= set(
        documento["paths"]["/equipes/{equipe_id}/composicao"]["put"]["responses"]
    )
    assert "422" in documento["paths"]["/equipes"]["post"]["responses"]
    esquemas = documento["components"]["schemas"]
    for nome in ("EquipeCreate", "ComposicaoUpdate", "IntegranteIndicado"):
        assert esquemas[nome]["additionalProperties"] is False
    assert set(esquemas["CategoriaEquipe"]["enum"]) == {"ESTUDANTES", "PROFISSIONAIS", "MISTA"}
    assert set(esquemas["TipoIntegrante"]["enum"]) == {"ESTUDANTE", "PROFISSIONAL"}


def test_migration_preserva_dados_legados_e_barra_politica_vazia():
    async def verificar(conn):
        hackathon = await novo_hackathon(conn)
        usuario = await novo_usuario(conn)
        equipe = await sql_na_transacao(
            conn, "INSERT INTO equipes (hackathon_id) VALUES (:h) RETURNING id", h=hackathon
        )
        await sql_na_transacao(
            conn,
            "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id, funcao)"
            " VALUES (:e, :u, :h, 'LIDER')",
            e=equipe,
            u=usuario,
            h=hackathon,
        )
        # Linhas gravadas como antes da BE-S5-01 entram como estudantes
        assert (
            await sql_na_transacao(
                conn, "SELECT categoria::text FROM equipes WHERE id = :e", e=equipe
            )
            == "ESTUDANTES"
        )
        assert (
            await sql_na_transacao(
                conn,
                "SELECT tipo_integrante::text FROM membros_equipe WHERE equipe_id = :e",
                e=equipe,
            )
            == "ESTUDANTE"
        )
        assert await sql_na_transacao(
            conn,
            "SELECT aceita_equipe_estudantes AND aceita_equipe_profissionais"
            " AND aceita_equipe_mista FROM hackathon WHERE id = :h",
            h=hackathon,
        )
        with pytest.raises(IntegrityError, match="ck_hackathon_categorias"):
            async with conn.begin_nested():
                await sql_na_transacao(
                    conn,
                    "UPDATE hackathon SET aceita_equipe_estudantes = false,"
                    " aceita_equipe_profissionais = false, aceita_equipe_mista = false"
                    " WHERE id = :h",
                    h=hackathon,
                )

    rodar(verificar)
