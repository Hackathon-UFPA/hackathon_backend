"""BE-S4-03, etapa 2: membros entram pelo fluxo real de convites e aceite de termos."""

from uuid import uuid4

import pytest

from app.const.enums import FuncaoMembro, SituacaoEquipe, StatusHackathon
from tests.test_convites import Cenario, com_token


class CenarioMembros(Cenario):
    @property
    def url(self):
        return f"/equipes/{self.equipe_id}/membros"

    def requisitar(self, client, metodo, *, quem=None, alvo=None, dados=None):
        url = self.url if metodo == "get" else f"{self.url}/{alvo or self.integrante['id']}"
        kwargs = (
            {"json": dados if dados is not None else {"funcao": "DESIGNER"}}
            if metodo == "patch"
            else {}
        )
        return getattr(client, metodo)(url, headers=com_token((quem or self.lider)["id"]), **kwargs)


@pytest.fixture
def membros(client, sql, usuario_no_banco, novo_email):
    c = CenarioMembros(sql, usuario_no_banco, novo_email)
    try:
        c.integrante, c.convite_id = c.convidar_usuario(client)
        assert c.aceitar(client, c.integrante, c.convite_id).status_code == 200
        yield c
    finally:
        c.limpar()


@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_alterar_membros_respeita_periodo_do_edital(
    client, membros, sql, periodo_inscricoes, metodo
):
    permitido = periodo_inscricoes(membros.hackathon_id)

    resposta = membros.requisitar(client, metodo)

    assert resposta.status_code == ((200 if metodo == "patch" else 204) if permitido else 409)
    if not permitido:
        assert resposta.json() == {"detail": "As inscrições deste hackathon não estão abertas."}
    atuais = sql(
        "SELECT funcao FROM membros_equipe WHERE equipe_id = :e AND usuario_id = :u",
        e=membros.equipe_id,
        u=membros.integrante["id"],
    )
    assert [m["funcao"] for m in atuais] == (
        (["DESIGNER"] if metodo == "patch" else []) if permitido else [None]
    )


@pytest.mark.parametrize("quem", ["lider", "integrante", "dev"])
def test_listar_membros_restritos_a_equipe(client, membros, usuario_no_banco, quem):
    outro_lider = usuario_no_banco()
    outra = membros.criar_equipe(membros.hackathon_id, outro_lider)
    usuario = usuario_no_banco(papel="DEV") if quem == "dev" else getattr(membros, quem)

    resposta = membros.requisitar(client, "get", quem=usuario)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert {m["usuario_id"] for m in corpo} == {
        str(membros.lider["id"]),
        str(membros.integrante["id"]),
    }
    assert {m["equipe_id"] for m in corpo} == {str(membros.equipe_id)}
    assert all(m["equipe_id"] != str(outra) for m in corpo)
    assert {m["funcao"] for m in corpo} == {"LIDER", None}
    assert all(
        set(m) == {"equipe_id", "usuario_id", "hackathon_id", "funcao", "entrou_em"} for m in corpo
    )


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "ORGANIZADOR", "COMITE_CIENTIFICO"])
def test_estranho_nao_lista_membros(client, membros, usuario_no_banco, papel):
    resposta = membros.requisitar(client, "get", quem=usuario_no_banco(papel=papel))
    assert resposta.status_code == 403
    assert str(membros.integrante["id"]) not in resposta.text


@pytest.mark.parametrize("funcao", [f.value for f in FuncaoMembro if f != "LIDER"] + [None])
def test_lider_altera_funcao_sem_mudar_identidade_ou_quantidade(client, membros, sql, funcao):
    antes = sql(
        "SELECT * FROM membros_equipe WHERE equipe_id = :e AND usuario_id = :u",
        e=membros.equipe_id,
        u=membros.integrante["id"],
    )[0]
    resposta = membros.requisitar(client, "patch", dados={"funcao": funcao})
    assert resposta.status_code == 200
    assert resposta.json()["funcao"] == funcao
    depois = sql(
        "SELECT * FROM membros_equipe WHERE equipe_id = :e AND usuario_id = :u",
        e=membros.equipe_id,
        u=membros.integrante["id"],
    )[0]
    assert depois["funcao"] == funcao
    for campo in ["equipe_id", "usuario_id", "hackathon_id", "entrou_em"]:
        assert depois[campo] == antes[campo]
    assert len(membros.requisitar(client, "get").json()) == 2


def test_patch_vazio_preserva_funcao_e_null_limpa_funcao(client, membros):
    assert membros.requisitar(client, "patch", dados={"funcao": "DESIGNER"}).status_code == 200
    assert membros.requisitar(client, "patch", dados={}).json()["funcao"] == "DESIGNER"
    resposta = membros.requisitar(client, "patch", dados={"funcao": None})
    assert resposta.status_code == 200
    assert resposta.json()["funcao"] is None


@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_dev_altera_membro_sem_vinculo(client, membros, usuario_no_banco, metodo):
    resposta = membros.requisitar(client, metodo, quem=usuario_no_banco(papel="DEV"))
    assert resposta.status_code == (200 if metodo == "patch" else 204)


def test_remover_abaixo_do_minimo_preserva_lider_e_revoga_acesso(client, membros, sql):
    # Sem limites fixos: o mínimo configurado é maior que a equipe em formação.
    sql(
        "UPDATE hackathon SET min_integrantes = 7, max_integrantes = 9 WHERE id = :h",
        h=membros.hackathon_id,
    )
    resposta = membros.requisitar(client, "delete")
    assert resposta.status_code == 204
    assert resposta.content == b""
    restantes = membros.requisitar(client, "get").json()
    assert [(m["usuario_id"], m["funcao"]) for m in restantes] == [
        (str(membros.lider["id"]), "LIDER"),
    ]
    assert membros.requisitar(client, "get", quem=membros.integrante).status_code == 403
    headers = com_token(membros.integrante["id"])
    assert client.get(f"/equipes/{membros.equipe_id}", headers=headers).status_code == 403
    assert client.get(f"/equipes/{membros.equipe_id}/convites", headers=headers).status_code == 403
    assert client.get("/equipes/minhas", headers=headers).json() == []
    assert membros.requisitar(client, "delete").status_code == 404


@pytest.mark.parametrize("metodo", ["patch", "delete"])
@pytest.mark.parametrize("quem", ["integrante", "intruso", "outro_lider"])
def test_apenas_lider_da_propria_equipe_altera(client, membros, usuario_no_banco, metodo, quem):
    if quem == "integrante":
        usuario = membros.integrante
    else:
        usuario = usuario_no_banco()
        if quem == "outro_lider":
            membros.criar_equipe(membros.hackathon_id, usuario)
    resposta = membros.requisitar(client, metodo, quem=usuario)
    assert resposta.status_code == 403
    assert len(membros.requisitar(client, "get").json()) == 2
    integrante = next(
        m
        for m in membros.requisitar(client, "get").json()
        if m["usuario_id"] == str(membros.integrante["id"])
    )
    assert integrante["funcao"] is None


@pytest.mark.parametrize("metodo", ["get", "patch", "delete"])
@pytest.mark.parametrize("autenticacao", ["ausente", "invalida", "pendente", "desativada"])
def test_exigir_token_e_conta_ativa(client, membros, usuario_no_banco, metodo, autenticacao):
    if autenticacao == "ausente":
        headers = {}
    elif autenticacao == "invalida":
        headers = {"Authorization": "Bearer invalido"}
    else:
        usuario = (
            usuario_no_banco(situacao_conta="PENDENTE")
            if autenticacao == "pendente"
            else usuario_no_banco(ativo=False)
        )
        headers = com_token(usuario["id"])
    url = membros.url if metodo == "get" else f"{membros.url}/{membros.integrante['id']}"
    kwargs = {"json": {"funcao": "DESIGNER"}} if metodo == "patch" else {}
    resposta = getattr(client, metodo)(url, headers=headers, **kwargs)
    assert resposta.status_code == (403 if autenticacao == "pendente" else 401)


@pytest.mark.parametrize("quem", ["lider", "dev"])
@pytest.mark.parametrize("funcao", [f.value for f in FuncaoMembro if f != "LIDER"] + [None])
def test_nao_rebaixar_lider(client, membros, usuario_no_banco, quem, funcao):
    usuario = membros.lider if quem == "lider" else usuario_no_banco(papel="DEV")
    resposta = membros.requisitar(
        client, "patch", quem=usuario, alvo=membros.lider["id"], dados={"funcao": funcao}
    )
    assert resposta.status_code == 409
    lider = next(
        m
        for m in membros.requisitar(client, "get").json()
        if m["usuario_id"] == str(membros.lider["id"])
    )
    assert lider["funcao"] == "LIDER"


@pytest.mark.parametrize("quem", ["lider", "dev"])
def test_nao_remover_lider(client, membros, usuario_no_banco, quem):
    usuario = membros.lider if quem == "lider" else usuario_no_banco(papel="DEV")
    assert (
        membros.requisitar(client, "delete", quem=usuario, alvo=membros.lider["id"]).status_code
        == 409
    )
    assert len(membros.requisitar(client, "get").json()) == 2


@pytest.mark.parametrize("quem", ["lider", "dev"])
def test_nao_promover_outro_membro_a_lider(client, membros, usuario_no_banco, quem):
    usuario = membros.lider if quem == "lider" else usuario_no_banco(papel="DEV")
    resposta = membros.requisitar(client, "patch", quem=usuario, dados={"funcao": "LIDER"})
    assert resposta.status_code == 409
    assert [
        m["usuario_id"] for m in membros.requisitar(client, "get").json() if m["funcao"] == "LIDER"
    ] == [str(membros.lider["id"])]


def test_reenviar_funcao_lider_e_idempotente(client, membros):
    resposta = membros.requisitar(
        client, "patch", alvo=membros.lider["id"], dados={"funcao": "LIDER"}
    )
    assert resposta.status_code == 200
    assert resposta.json()["funcao"] == "LIDER"


@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_nao_alterar_usuario_de_outra_equipe(client, membros, usuario_no_banco, sql, metodo):
    outro_usuario = usuario_no_banco()
    outra_equipe = membros.criar_equipe(membros.hackathon_id, outro_usuario)
    resposta = membros.requisitar(client, metodo, alvo=outro_usuario["id"])
    assert resposta.status_code == 404
    assert (
        sql(
            "SELECT funcao FROM membros_equipe WHERE equipe_id = :e AND usuario_id = :u",
            e=outra_equipe,
            u=outro_usuario["id"],
        )[0]["funcao"]
        == "LIDER"
    )


@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_alteracao_nao_afeta_vinculo_do_mesmo_usuario_em_outra_edicao(client, membros, sql, metodo):
    outra_edicao = membros.criar_hackathon()
    outra_equipe = membros.criar_equipe(outra_edicao, membros.integrante)
    assert membros.requisitar(client, metodo).status_code == (200 if metodo == "patch" else 204)
    assert (
        sql(
            "SELECT funcao FROM membros_equipe WHERE equipe_id = :e AND usuario_id = :u",
            e=outra_equipe,
            u=membros.integrante["id"],
        )[0]["funcao"]
        == "LIDER"
    )


@pytest.mark.parametrize("metodo", ["get", "patch", "delete"])
def test_equipe_inexistente(client, membros, metodo):
    membros.equipe_id = uuid4()
    assert membros.requisitar(client, metodo).status_code == 404


@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_usuario_sem_vinculo_nao_e_adicionado(client, membros, metodo, usuario_no_banco):
    usuario = usuario_no_banco()
    assert membros.requisitar(client, metodo, alvo=usuario["id"]).status_code == 404
    assert len(membros.requisitar(client, "get").json()) == 2


@pytest.mark.parametrize("status", [s.value for s in StatusHackathon if s != "INSCRICOES"])
@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_composicao_fechada_fora_das_inscricoes(client, membros, metodo, status):
    membros.definir_status(status)
    assert membros.requisitar(client, metodo).status_code == 409
    assert len(membros.requisitar(client, "get").json()) == 2


@pytest.mark.parametrize("situacao", [s.value for s in SituacaoEquipe if s != "EM_FORMACAO"])
@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_composicao_fechada_fora_de_formacao(client, membros, sql, metodo, situacao):
    sql(
        "UPDATE equipes SET situacao = CAST(:s AS situacao_equipe) WHERE id = :e",
        s=situacao,
        e=membros.equipe_id,
    )
    assert membros.requisitar(client, metodo).status_code == 409
    assert len(membros.requisitar(client, "get").json()) == 2


@pytest.mark.parametrize("restricao", ["prazo", "situacao"])
@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_dev_tambem_respeita_periodo_e_situacao(
    client,
    membros,
    sql,
    usuario_no_banco,
    restricao,
    metodo,
):
    if restricao == "prazo":
        membros.definir_status("INSCRICOES_ENCERRADAS")
    else:
        sql("UPDATE equipes SET situacao = 'HOMOLOGADA' WHERE id = :e", e=membros.equipe_id)
    dev = usuario_no_banco(papel="DEV")
    assert membros.requisitar(client, metodo, quem=dev).status_code == 409


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("equipe_id", str(uuid4())),
        ("usuario_id", str(uuid4())),
        ("hackathon_id", str(uuid4())),
        ("entrou_em", "2026-10-28T00:00:00Z"),
        ("papel", "DEV"),
        ("funcao", "INEXISTENTE"),
    ],
)
def test_patch_rejeita_campos_indevidos(client, membros, campo, valor):
    resposta = membros.requisitar(client, "patch", dados={"funcao": "DESIGNER", campo: valor})
    assert resposta.status_code == 422
    assert all(m["funcao"] != "DESIGNER" for m in membros.requisitar(client, "get").json())


def test_nao_existe_inclusao_direta(client, membros, usuario_no_banco):
    usuario = usuario_no_banco()
    resposta = client.post(
        membros.url,
        headers=com_token(membros.lider["id"]),
        json={"usuario_id": str(usuario["id"]), "funcao": "DESIGNER"},
    )
    assert resposta.status_code == 405
    assert len(membros.requisitar(client, "get").json()) == 2


def test_remocao_preserva_historico_e_reconvite_a_mesma_equipe_fica_bloqueado(client, membros, sql):
    convite_antes = sql("SELECT * FROM convites WHERE id = :id", id=membros.convite_id)[0]
    aceites_antes = sql(
        "SELECT * FROM aceites_termos WHERE usuario_id = :u ORDER BY termo_id",
        u=membros.integrante["id"],
    )
    assert len(aceites_antes) == 2
    assert membros.requisitar(client, "delete").status_code == 204
    assert sql("SELECT * FROM convites WHERE id = :id", id=membros.convite_id)[0] == convite_antes
    assert (
        sql(
            "SELECT * FROM aceites_termos WHERE usuario_id = :u ORDER BY termo_id",
            u=membros.integrante["id"],
        )
        == aceites_antes
    )
    # O índice parcial inclui ACEITO; remover o vínculo não muda o fato histórico do aceite.
    resposta = membros.convidar(client, email=membros.integrante["email"].upper())
    assert resposta.status_code == 409
    assert membros.aceitar(client, membros.integrante, membros.convite_id).status_code == 409
    convites = client.get(
        f"/equipes/{membros.equipe_id}/convites", headers=com_token(membros.lider["id"])
    ).json()
    assert [(c["id"], c["status"]) for c in convites] == [(membros.convite_id, "ACEITO")]


def test_remocao_libera_vaga_mantendo_maximo_configurado(client, membros):
    membros.definir_maximo(2)
    assert membros.convidar(client).status_code == 409
    assert membros.requisitar(client, "patch").status_code == 200  # no máximo, sem adicionar
    assert membros.requisitar(client, "delete").status_code == 204
    convidado, convite_id = membros.convidar_usuario(client)
    assert membros.aceitar(client, convidado, convite_id).status_code == 200
    assert len(membros.requisitar(client, "get").json()) == 2
    assert membros.convidar(client).status_code == 409


def test_remover_permite_corrigir_equipe_com_maximo_reduzido(client, membros):
    membros.definir_maximo(1)
    assert membros.requisitar(client, "delete").status_code == 204
    assert len(membros.requisitar(client, "get").json()) == 1
    assert membros.convidar(client).status_code == 409


def test_removido_pode_aceitar_convite_de_outra_equipe_da_mesma_edicao(
    client,
    membros,
    usuario_no_banco,
):
    outro_lider = usuario_no_banco()
    outra_equipe = membros.criar_equipe(membros.hackathon_id, outro_lider)
    resposta = client.post(
        f"/equipes/{outra_equipe}/convites",
        headers=com_token(outro_lider["id"]),
        json={"nome": "Integrante", "email": membros.integrante["email"]},
    )
    assert resposta.status_code == 201
    convite_id = resposta.json()["id"]
    assert membros.aceitar(client, membros.integrante, convite_id).status_code == 409
    assert membros.requisitar(client, "delete").status_code == 204
    assert membros.aceitar(client, membros.integrante, convite_id).status_code == 200
    resposta = client.get("/equipes/minhas", headers=com_token(membros.integrante["id"]))
    assert [e["id"] for e in resposta.json()] == [str(outra_equipe)]


@pytest.mark.parametrize(
    "metodo,controller", [("patch", "atualizar_membro"), ("delete", "remover_membro")]
)
def test_falha_depois_do_flush_reverte_alteracao(
    client, membros, sql, monkeypatch, metodo, controller
):
    from app.controllers import membro_equipe

    original = getattr(membro_equipe, controller)

    async def falhar(*args):
        await original(*args)
        raise RuntimeError("Falha depois do flush")

    with monkeypatch.context() as patch:
        patch.setattr(f"app.services.membro_equipe.{controller}", falhar)
        with pytest.raises(RuntimeError, match="Falha depois do flush"):
            membros.requisitar(client, metodo)
    atual = sql(
        "SELECT funcao FROM membros_equipe WHERE equipe_id = :e AND usuario_id = :u",
        e=membros.equipe_id,
        u=membros.integrante["id"],
    )
    assert len(atual) == 1
    assert atual[0]["funcao"] is None
    assert membros.requisitar(client, metodo).status_code == (200 if metodo == "patch" else 204)


def test_swagger_documenta_membros_e_restricoes(client):
    doc = client.get("/openapi.json").json()
    raiz = "/equipes/{equipe_id}/membros"
    for caminho, metodos in {raiz: ["get"], f"{raiz}/{{usuario_id}}": ["patch", "delete"]}.items():
        for metodo in metodos:
            rota = doc["paths"][caminho][metodo]
            assert rota["tags"] == ["Equipes"]
            assert rota["security"]
            assert {"401", "403", "404", "422"} <= set(rota["responses"])
    assert "content" not in doc["paths"][f"{raiz}/{{usuario_id}}"]["delete"]["responses"]["204"]
    assert doc["components"]["schemas"]["MembroEquipeUpdate"]["additionalProperties"] is False
