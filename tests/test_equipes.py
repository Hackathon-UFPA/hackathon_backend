"""Primeira etapa da BE-S4-03: API e persistência no PostgreSQL de testes."""

from uuid import uuid4

import pytest

from app.const.enums import SituacaoEquipe, StatusHackathon
from app.security.token import criar_token


def com_token(usuario):
    return {"Authorization": f"Bearer {criar_token(usuario['id'])}"}


@pytest.fixture
def equipes(sql, usuario_no_banco):
    hackathons = []

    class Cenario:
        def hackathon(self, status="INSCRICOES", minimo=7, maximo=9):
            id_ = sql(
                "INSERT INTO hackathon (nome, status, min_integrantes, max_integrantes)"
                " VALUES ('Teste de equipes', CAST(:s AS status_hackathon), :min, :max)"
                " RETURNING id",
                s=status,
                min=minimo,
                max=maximo,
            )[0]["id"]
            hackathons.append(id_)
            return id_

        def criar(self, client, usuario=None, hackathon=None, **campos):
            return client.post(
                "/equipes",
                headers=com_token(usuario or self.lider),
                json={"hackathon_id": str(hackathon or self.hackathon_id), **campos},
            )

    cenario = Cenario()
    cenario.lider = usuario_no_banco()
    cenario.hackathon_id = cenario.hackathon()
    yield cenario
    for hackathon_id in hackathons:
        sql(
            "DELETE FROM convites WHERE equipe_id IN"
            " (SELECT id FROM equipes WHERE hackathon_id = :h)",
            h=hackathon_id,
        )
        sql("DELETE FROM membros_equipe WHERE hackathon_id = :h", h=hackathon_id)
        sql("DELETE FROM equipes WHERE hackathon_id = :h", h=hackathon_id)
        sql("DELETE FROM hackathon WHERE id = :h", h=hackathon_id)


def test_criar_equipe_com_lider_automatico_sem_minimo_ou_termos(client, equipes, sql):
    resposta = equipes.criar(client, nome="Equipe UFPA")

    assert resposta.status_code == 201, resposta.text
    equipe = resposta.json()
    assert equipe["nome"] == "Equipe UFPA"
    assert equipe["hackathon_id"] == str(equipes.hackathon_id)
    assert equipe["situacao"] == "EM_FORMACAO"
    assert equipe["inscricao_concluida_em"] is None
    assert equipe["homologada_em"] is None
    assert equipe["criado_em"] is not None
    membros = sql("SELECT * FROM membros_equipe WHERE equipe_id = :e", e=equipe["id"])
    assert len(membros) == 1
    assert membros[0]["usuario_id"] == equipes.lider["id"]
    assert membros[0]["hackathon_id"] == equipes.hackathon_id
    assert membros[0]["funcao"] == "LIDER"
    assert sql("SELECT * FROM aceites_termos WHERE usuario_id = :u", u=equipes.lider["id"]) == []


def test_criar_sem_nome_e_com_maximo_configurado_em_um(client, equipes):
    hackathon = equipes.hackathon(minimo=1, maximo=1)
    resposta = equipes.criar(client, hackathon=hackathon)
    assert resposta.status_code == 201
    assert resposta.json()["nome"] is None


@pytest.mark.parametrize("funcao", ["LIDER", "DESENVOLVEDOR", None])
def test_impedir_segundo_vinculo_na_mesma_edicao(client, equipes, sql, funcao):
    primeira = equipes.criar(client).json()
    sql(
        "UPDATE membros_equipe SET funcao = CAST(:f AS funcao_membro) WHERE equipe_id = :e",
        f=funcao,
        e=primeira["id"],
    )

    resposta = equipes.criar(client)

    assert resposta.status_code == 409
    assert (
        sql("SELECT count(*) AS n FROM equipes WHERE hackathon_id = :h", h=equipes.hackathon_id)[0][
            "n"
        ]
        == 1
    )


def test_participar_em_edicoes_diferentes_e_listar_apenas_minhas(client, equipes, usuario_no_banco):
    primeira = equipes.criar(client).json()
    segunda = equipes.criar(client, hackathon=equipes.hackathon()).json()
    terceira = equipes.criar(client, usuario=usuario_no_banco()).json()

    resposta = client.get("/equipes/minhas", headers=com_token(equipes.lider))

    assert resposta.status_code == 200
    assert {e["id"] for e in resposta.json()} == {primeira["id"], segunda["id"]}
    assert terceira["id"] not in {e["id"] for e in resposta.json()}
    assert all(
        "email" not in e and "membros" not in e and "convites" not in e for e in resposta.json()
    )


def test_minhas_inclui_integrante_sem_funcao_de_lider(client, equipes, usuario_no_banco, sql):
    equipe = equipes.criar(client).json()
    integrante = usuario_no_banco()
    sql(
        "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id) VALUES (:e, :u, :h)",
        e=equipe["id"],
        u=integrante["id"],
        h=equipes.hackathon_id,
    )
    resposta = client.get("/equipes/minhas", headers=com_token(integrante))
    assert resposta.status_code == 200
    assert [e["id"] for e in resposta.json()] == [equipe["id"]]
    assert client.get(f"/equipes/{equipe['id']}", headers=com_token(integrante)).status_code == 200


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "DEV"])
def test_minhas_sem_vinculo_retorna_lista_vazia(client, equipes, usuario_no_banco, papel):
    equipes.criar(client)
    resposta = client.get("/equipes/minhas", headers=com_token(usuario_no_banco(papel=papel)))
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_consultar_equipe_por_lider(client, equipes):
    equipe = equipes.criar(client).json()
    resposta = client.get(f"/equipes/{equipe['id']}", headers=com_token(equipes.lider))
    assert resposta.status_code == 200
    assert resposta.json() == equipe


def test_intruso_nao_consulta_dados_da_equipe(client, equipes, usuario_no_banco):
    equipe = equipes.criar(client, nome="Equipe privada").json()
    resposta = client.get(f"/equipes/{equipe['id']}", headers=com_token(usuario_no_banco()))
    assert resposta.status_code == 403
    assert equipe["nome"] not in resposta.text


def test_dev_consulta_e_edita_sem_ser_integrante(client, equipes, usuario_no_banco):
    equipe = equipes.criar(client).json()
    headers = com_token(usuario_no_banco(papel="DEV"))
    assert client.get(f"/equipes/{equipe['id']}", headers=headers).status_code == 200
    resposta = client.patch(f"/equipes/{equipe['id']}", headers=headers, json={"nome": "Novo"})
    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Novo"


@pytest.mark.parametrize("metodo", ["get", "patch"])
def test_equipe_inexistente(client, equipes, metodo):
    kwargs = {"json": {"nome": "Novo"}} if metodo == "patch" else {}
    resposta = getattr(client, metodo)(
        f"/equipes/{uuid4()}", headers=com_token(equipes.lider), **kwargs
    )
    assert resposta.status_code == 404


def test_criar_com_hackathon_inexistente(client, equipes):
    assert equipes.criar(client, hackathon=uuid4()).status_code == 404


def test_lider_edita_somente_nome_sem_exigir_minimo(client, equipes, sql):
    equipe = equipes.criar(client, nome="Antigo").json()
    resposta = client.patch(
        f"/equipes/{equipe['id']}", headers=com_token(equipes.lider), json={"nome": "Novo"}
    )
    assert resposta.status_code == 200
    atual = resposta.json()
    assert atual["nome"] == "Novo"
    assert atual["atualizado_em"] is not None
    for campo in [
        "id",
        "hackathon_id",
        "situacao",
        "criado_em",
        "inscricao_concluida_em",
        "homologada_em",
    ]:
        assert atual[campo] == equipe[campo]
    assert sql("SELECT nome FROM equipes WHERE id = :e", e=equipe["id"])[0]["nome"] == "Novo"


def test_patch_vazio_preserva_equipe_e_nome_nulo_e_permitido(client, equipes):
    equipe = equipes.criar(client, nome="Nome").json()
    url = f"/equipes/{equipe['id']}"
    assert client.patch(url, headers=com_token(equipes.lider), json={}).json() == equipe
    resposta = client.patch(url, headers=com_token(equipes.lider), json={"nome": None})
    assert resposta.status_code == 200
    assert resposta.json()["nome"] is None


@pytest.mark.parametrize("integrante", [False, True])
def test_apenas_lider_edita(client, equipes, usuario_no_banco, sql, integrante):
    equipe = equipes.criar(client, nome="Original").json()
    usuario = usuario_no_banco()
    if integrante:
        sql(
            "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id) VALUES (:e,:u,:h)",
            e=equipe["id"],
            u=usuario["id"],
            h=equipes.hackathon_id,
        )
    resposta = client.patch(
        f"/equipes/{equipe['id']}", headers=com_token(usuario), json={"nome": "Alterado"}
    )
    assert resposta.status_code == 403
    assert sql("SELECT nome FROM equipes WHERE id = :e", e=equipe["id"])[0]["nome"] == "Original"


@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("post", "/equipes"),
        ("get", "/equipes/minhas"),
        ("get", "/equipes/{id}"),
        ("patch", "/equipes/{id}"),
    ],
)
@pytest.mark.parametrize("pendente", [False, True])
def test_exigir_login_e_conta_ativa(client, equipes, usuario_no_banco, metodo, caminho, pendente):
    equipe = equipes.criar(client).json()
    headers = com_token(usuario_no_banco(situacao_conta="PENDENTE")) if pendente else {}
    kwargs = {}
    if metodo == "post":
        kwargs["json"] = {"hackathon_id": str(equipes.hackathon_id)}
    elif metodo == "patch":
        kwargs["json"] = {"nome": "Novo"}
    resposta = getattr(client, metodo)(caminho.format(id=equipe["id"]), headers=headers, **kwargs)
    assert resposta.status_code == (403 if pendente else 401)


@pytest.mark.parametrize("status", [s.value for s in StatusHackathon if s != "INSCRICOES"])
def test_criar_fora_das_inscricoes(client, equipes, status, sql):
    hackathon = equipes.hackathon(status=status)
    assert equipes.criar(client, hackathon=hackathon).status_code == 409
    assert sql("SELECT * FROM equipes WHERE hackathon_id = :h", h=hackathon) == []


@pytest.mark.parametrize("status", [s.value for s in StatusHackathon if s != "INSCRICOES"])
def test_editar_fora_das_inscricoes(client, equipes, sql, status):
    equipe = equipes.criar(client).json()
    sql(
        "UPDATE hackathon SET status = CAST(:s AS status_hackathon) WHERE id = :h",
        s=status,
        h=equipes.hackathon_id,
    )
    resposta = client.patch(
        f"/equipes/{equipe['id']}", headers=com_token(equipes.lider), json={"nome": "Novo"}
    )
    assert resposta.status_code == 409
    assert sql("SELECT nome FROM equipes WHERE id = :e", e=equipe["id"])[0]["nome"] is None


@pytest.mark.parametrize("situacao", [s.value for s in SituacaoEquipe if s != "EM_FORMACAO"])
def test_editar_apenas_em_formacao(client, equipes, sql, situacao):
    equipe = equipes.criar(client).json()
    sql(
        "UPDATE equipes SET situacao = CAST(:s AS situacao_equipe) WHERE id = :e",
        s=situacao,
        e=equipe["id"],
    )
    resposta = client.patch(
        f"/equipes/{equipe['id']}", headers=com_token(equipes.lider), json={"nome": "Novo"}
    )
    assert resposta.status_code == 409
    assert sql("SELECT nome FROM equipes WHERE id = :e", e=equipe["id"])[0]["nome"] is None


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("lider_id", str(uuid4())),
        ("usuario_id", str(uuid4())),
        ("funcao", "LIDER"),
        ("situacao", "HOMOLOGADA"),
        ("criado_em", "2026-01-01T00:00:00"),
        ("atualizado_em", "2026-01-01T00:00:00"),
        ("inscricao_concluida_em", "2026-01-01T00:00:00"),
        ("homologada_em", "2026-01-01T00:00:00"),
    ],
)
def test_criacao_rejeita_campos_controlados_pelo_sistema(client, equipes, campo, valor, sql):
    assert equipes.criar(client, **{campo: valor}).status_code == 422
    assert sql("SELECT * FROM equipes WHERE hackathon_id = :h", h=equipes.hackathon_id) == []


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("hackathon_id", str(uuid4())),
        ("situacao", "HOMOLOGADA"),
        ("criado_em", None),
        ("atualizado_em", None),
        ("inscricao_concluida_em", None),
        ("homologada_em", None),
        ("lider_id", str(uuid4())),
    ],
)
def test_patch_rejeita_campos_controlados_pelo_sistema(client, equipes, campo, valor):
    equipe = equipes.criar(client, nome="Original").json()
    url = f"/equipes/{equipe['id']}"
    resposta = client.patch(
        url, headers=com_token(equipes.lider), json={"nome": "Alterado", campo: valor}
    )
    assert resposta.status_code == 422
    assert client.get(url, headers=com_token(equipes.lider)).json() == equipe


@pytest.mark.parametrize("metodo", ["post", "patch"])
def test_rejeitar_nome_acima_do_limite(client, equipes, metodo):
    if metodo == "post":
        resposta = equipes.criar(client, nome="a" * 256)
    else:
        equipe = equipes.criar(client).json()
        resposta = client.patch(
            f"/equipes/{equipe['id']}", headers=com_token(equipes.lider), json={"nome": "a" * 256}
        )
    assert resposta.status_code == 422


def test_rollback_sem_equipe_orfa_quando_unicidade_e_decidida_pelo_banco(
    client,
    equipes,
    sql,
    monkeypatch,
):
    equipes.criar(client)

    async def sem_vinculo(*args):
        return None

    # Simula leitura sem vínculo antes de outra criação/aceite confirmar a participação.
    monkeypatch.setattr("app.services.equipe.get_membro_no_hackathon", sem_vinculo)
    resposta = equipes.criar(client)
    assert resposta.status_code == 409
    assert (
        sql("SELECT count(*) AS n FROM equipes WHERE hackathon_id = :h", h=equipes.hackathon_id)[0][
            "n"
        ]
        == 1
    )
    assert (
        sql(
            "SELECT count(*) AS n FROM membros_equipe WHERE hackathon_id = :h",
            h=equipes.hackathon_id,
        )[0]["n"]
        == 1
    )


def test_rollback_em_falha_apos_persistir_equipe(client, equipes, sql, monkeypatch):
    def falhar(*args):
        raise RuntimeError("Falha ao adicionar líder")

    with monkeypatch.context() as patch:
        patch.setattr("app.services.equipe.adicionar_membro", falhar)
        with pytest.raises(RuntimeError, match="Falha ao adicionar líder"):
            equipes.criar(client)
    assert sql("SELECT * FROM equipes WHERE hackathon_id = :h", h=equipes.hackathon_id) == []
    assert sql("SELECT * FROM membros_equipe WHERE hackathon_id = :h", h=equipes.hackathon_id) == []
    assert equipes.criar(client).status_code == 201


def test_equipe_criada_permite_enviar_e_listar_convites(client, equipes, usuario_no_banco):
    equipe = equipes.criar(client).json()
    url = f"/equipes/{equipe['id']}/convites"
    resposta = client.post(
        url,
        headers=com_token(equipes.lider),
        json={"nome": "Convidada", "email": usuario_no_banco()["email"]},
    )
    assert resposta.status_code == 201
    listagem = client.get(url, headers=com_token(equipes.lider))
    assert listagem.status_code == 200
    assert [c["id"] for c in listagem.json()] == [resposta.json()["id"]]


def test_swagger_documenta_endpoints_e_rejeicao_de_campos(client):
    documento = client.get("/openapi.json").json()
    for caminho, metodos in {
        "/equipes": ["post"],
        "/equipes/minhas": ["get"],
        "/equipes/{equipe_id}": ["get", "patch"],
    }.items():
        for metodo in metodos:
            rota = documento["paths"][caminho][metodo]
            assert rota["tags"] == ["Equipes"]
            assert rota["security"]
            assert {"401", "403"} <= set(rota["responses"])
            if caminho != "/equipes/minhas":
                assert "422" in rota["responses"]
    for schema in ["EquipeCreate", "EquipeUpdate"]:
        assert documento["components"]["schemas"][schema]["additionalProperties"] is False
