"""BE-S4-12: notificação do resultado (RF33) e modo somente leitura das equipes não aprovadas
(RF34)."""

import pytest

from tests.test_convites import com_token
from tests.test_resultado import CenarioResultado


@pytest.fixture
def resultado(sql, usuario_no_banco):
    cenario = CenarioResultado(sql, usuario_no_banco)
    cenario.avaliar_tudo()
    try:
        yield cenario
    finally:
        for tabela in ("convites", "protocolos"):
            cenario.sql(
                f"DELETE FROM {tabela} WHERE equipe_id IN"
                " (SELECT id FROM equipes WHERE hackathon_id = :h)",
                h=cenario.hackathon_id,
            )
        cenario.limpar()


class Equipes:
    """Equipes do cenário: propostas[0] é aprovada; propostas[1] e [2] são reprovadas."""

    def __init__(self, cenario: CenarioResultado, usuario_no_banco):
        self.c = cenario
        self.usuario_no_banco = usuario_no_banco

    def equipe(self, proposta) -> dict:
        equipe_id = self.c.sql("SELECT equipe_id FROM submissoes WHERE id = :s", s=proposta)[0][
            "equipe_id"
        ]
        lider = self.c.sql(
            "SELECT usuario_id FROM membros_equipe WHERE equipe_id = :e AND funcao = 'LIDER'",
            e=equipe_id,
        )[0]["usuario_id"]
        return {"id": equipe_id, "lider": lider, "proposta": proposta}

    def com_membro(self, equipe: dict) -> dict:
        membro = self.usuario_no_banco(senha=None)
        self.c.sql(
            "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id, funcao)"
            " VALUES (:e, :u, :h, 'DESENVOLVEDOR')",
            e=equipe["id"],
            u=membro["id"],
            h=self.c.hackathon_id,
        )
        return membro

    def convite(self, equipe: dict, email: str, destinatario=None) -> object:
        return self.c.sql(
            "INSERT INTO convites (equipe_id, nome, email, usuario_id, convidado_por)"
            " VALUES (:e, 'Fulano', :m, :u, :l) RETURNING id",
            e=equipe["id"],
            m=email,
            u=destinatario["id"] if destinatario else None,
            l=equipe["lider"],
        )[0]["id"]


@pytest.fixture
def equipes(resultado, usuario_no_banco):
    return Equipes(resultado, usuario_no_banco)


def _homologar(client, resultado):
    resposta = resultado.homologar(client, [resultado.propostas[0]])
    assert resposta.status_code == 200, resposta.text


def _rotas_de_escrita(equipes, equipe):
    """(método, caminho, corpo) de cada rota de escrita ligada à equipe."""
    membro = equipes.com_membro(equipe)
    destinatario = equipes.usuario_no_banco(senha=None)
    cancelar = equipes.convite(equipe, "a@example.com")
    aceitar = equipes.convite(equipe, destinatario["email"], destinatario)
    recusante = equipes.usuario_no_banco(senha=None)
    recusar = equipes.convite(equipe, recusante["email"], recusante)
    base = f"/equipes/{equipe['id']}"
    return [
        ("PATCH", base, {"nome": "Outro nome"}, equipe["lider"]),
        ("PATCH", f"{base}/membros/{membro['id']}", {"funcao": "DESIGNER"}, equipe["lider"]),
        ("DELETE", f"{base}/membros/{membro['id']}", None, equipe["lider"]),
        (
            "POST",
            f"{base}/convites",
            {"nome": "Nova", "email": "nova@example.com"},
            equipe["lider"],
        ),
        ("POST", f"/convites/{cancelar}/cancelar", None, equipe["lider"]),
        (
            "POST",
            f"/convites/{aceitar}/aceitar",
            {"termos_ids": [str(equipes.c.hackathon_id)]},
            destinatario["id"],
        ),
        ("POST", f"/convites/{recusar}/recusar", None, recusante["id"]),
        ("POST", f"{base}/inscricao/concluir", None, equipe["lider"]),
        ("POST", f"{base}/proposta/rascunho", {}, equipe["lider"]),
        ("PATCH", f"{base}/proposta/rascunho", {"titulo": "Novo"}, equipe["lider"]),
        ("POST", f"{base}/proposta/enviar", None, equipe["lider"]),
    ]


def _chamar(client, metodo, caminho, corpo, usuario_id):
    return client.request(metodo, caminho, json=corpo, headers=com_token(usuario_id))


def _bloqueada(resposta) -> bool:
    return resposta.status_code == 409 and "somente leitura" in resposta.json()["detail"]


def test_equipe_reprovada_recebe_409_em_cada_rota_de_escrita(client, resultado, equipes):
    reprovada = equipes.equipe(resultado.propostas[1])
    rotas = _rotas_de_escrita(equipes, reprovada)
    _homologar(client, resultado)
    assert len(rotas) == 11
    for metodo, caminho, corpo, quem in rotas:
        resposta = _chamar(client, metodo, caminho, corpo, quem)
        assert _bloqueada(resposta), (metodo, caminho, resposta.status_code, resposta.text)


def test_dev_tambem_e_bloqueado_nas_rotas_de_escrita(client, resultado, equipes, usuario_no_banco):
    dev = usuario_no_banco(papel="DEV", senha=None)
    reprovada = equipes.equipe(resultado.propostas[1])
    base = f"/equipes/{reprovada['id']}"
    _homologar(client, resultado)
    for metodo, caminho, corpo in [
        ("PATCH", base, {"nome": "X"}),
        ("POST", f"{base}/inscricao/concluir", None),
        ("POST", f"{base}/proposta/rascunho", {}),
    ]:
        assert _bloqueada(_chamar(client, metodo, caminho, corpo, dev["id"])), caminho


def test_equipe_reprovada_continua_consultando(client, resultado, equipes):
    reprovada = equipes.equipe(resultado.propostas[1])
    base = f"/equipes/{reprovada['id']}"
    resultado.sql(
        "INSERT INTO protocolos (tipo, equipe_id, submissao_id, emitido_por, emitido_em)"
        " VALUES ('PROPOSTA', :e, :s, :u, now())",
        e=reprovada["id"],
        s=reprovada["proposta"],
        u=reprovada["lider"],
    )
    _homologar(client, resultado)
    for caminho in [
        base,
        f"{base}/membros",
        f"{base}/convites",
        f"{base}/painel",
        f"{base}/proposta",
        f"{base}/resultado",
        "/equipes/minhas",
        "/me/notificacoes",
    ]:
        resposta = client.get(caminho, headers=com_token(reprovada["lider"]))
        assert resposta.status_code == 200, (caminho, resposta.status_code, resposta.text)


def test_equipe_aprovada_e_hackathon_sem_homologacao_nao_sao_bloqueados(client, resultado, equipes):
    aprovada = equipes.equipe(resultado.propostas[0])
    reprovada = equipes.equipe(resultado.propostas[1])
    rotas_aprovada = _rotas_de_escrita(equipes, aprovada)
    rotas_antes = _rotas_de_escrita(equipes, reprovada)
    for metodo, caminho, corpo, quem in rotas_antes:  # ainda sem homologação
        assert not _bloqueada(_chamar(client, metodo, caminho, corpo, quem)), caminho
    _homologar(client, resultado)
    for metodo, caminho, corpo, quem in rotas_aprovada:
        assert not _bloqueada(_chamar(client, metodo, caminho, corpo, quem)), caminho


def test_equipe_sem_proposta_enviada_nao_e_bloqueada(client, resultado, equipes, usuario_no_banco):
    lider = usuario_no_banco(senha=None)
    equipe_id = resultado.sql(
        "INSERT INTO equipes (hackathon_id, nome) VALUES (:h, 'Sem proposta') RETURNING id",
        h=resultado.hackathon_id,
    )[0]["id"]
    resultado.sql(
        "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id, funcao)"
        " VALUES (:e, :u, :h, 'LIDER')",
        e=equipe_id,
        u=lider["id"],
        h=resultado.hackathon_id,
    )
    _homologar(client, resultado)
    resposta = client.patch(
        f"/equipes/{equipe_id}", json={"nome": "Novo"}, headers=com_token(lider["id"])
    )
    assert not _bloqueada(resposta), resposta.text
    # Sem proposta com resultado, a consulta do resultado da equipe responde 404
    consulta = client.get(f"/equipes/{equipe_id}/resultado", headers=com_token(lider["id"]))
    assert consulta.status_code == 404


def test_homologacao_cria_notificacao_para_todos_os_integrantes(client, resultado, equipes):
    aprovada = equipes.equipe(resultado.propostas[0])
    reprovada = equipes.equipe(resultado.propostas[1])
    extra_a = equipes.com_membro(aprovada)
    extra_r = equipes.com_membro(reprovada)
    _homologar(client, resultado)
    linhas = resultado.sql(
        "SELECT * FROM notificacoes_resultado WHERE hackathon_id = :h", h=resultado.hackathon_id
    )
    # 3 equipes com líder + 2 integrantes extras
    assert len(linhas) == 5
    assert {(n["equipe_id"], n["usuario_id"]) for n in linhas} >= {
        (aprovada["id"], extra_a["id"]),
        (reprovada["id"], extra_r["id"]),
    }
    for n in linhas:
        assert n["canal"] == "PLATAFORMA"
        assert n["status_envio"] == "ENVIADO"
        assert n["enviado_em"] is not None
        assert n["erro"] is None
        assert n["aprovada"] is (n["equipe_id"] == aprovada["id"])

    propria = client.get("/me/notificacoes", headers=com_token(extra_r["id"]))
    assert propria.status_code == 200
    [notificacao] = propria.json()
    assert notificacao["aprovada"] is False
    assert notificacao["status_envio"] == "ENVIADO"
    assert "NÃO foi aprovada" in notificacao["mensagem"]
    assert len(notificacao["pareceres"]) == 2
    # Outro usuário não vê notificações alheias
    assert (
        client.get("/me/notificacoes", headers=com_token(resultado.organizador["id"])).json() == []
    )


def test_falha_ao_notificar_desfaz_a_homologacao(client, resultado, monkeypatch):
    async def falha(*_, **__):
        raise RuntimeError("falha ao notificar")

    monkeypatch.setattr("app.services.resultado.criar_notificacoes_do_resultado", falha)
    with pytest.raises(RuntimeError):
        resultado.homologar(client, [resultado.propostas[0]])
    assert resultado.homologacoes() == []
    assert (
        resultado.sql(
            "SELECT 1 FROM resultados_proposta WHERE hackathon_id = :h", h=resultado.hackathon_id
        )
        == []
    )


def test_integrante_le_o_proprio_resultado_e_parecer(client, resultado, equipes):
    resultado.sql(
        "UPDATE avaliacoes SET comentarios = 'Parecer ' || id::text WHERE submissao_id = :s",
        s=resultado.propostas[1],
    )
    reprovada = equipes.equipe(resultado.propostas[1])
    caminho = f"/equipes/{reprovada['id']}/resultado"
    antes = client.get(caminho, headers=com_token(reprovada["lider"]))
    assert antes.status_code == 200
    assert antes.json()["divulgado"] is False
    assert antes.json()["pareceres"] == []
    assert antes.json()["aprovada"] is None

    _homologar(client, resultado)
    resposta = client.get(caminho, headers=com_token(reprovada["lider"]))
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["divulgado"] is True
    assert corpo["aprovada"] is False
    assert corpo["somente_leitura"] is True
    assert len(corpo["pareceres"]) == 2
    assert all(p["parecer"].startswith("Parecer ") for p in corpo["pareceres"])
    assert all(set(p) == {"parecer", "recomendacao"} for p in corpo["pareceres"])  # anônimo
    for campo in ("nota_media", "classificacao"):
        assert campo not in corpo


def test_outra_equipe_nao_acessa_o_resultado(client, resultado, equipes):
    a = equipes.equipe(resultado.propostas[0])
    b = equipes.equipe(resultado.propostas[1])
    _homologar(client, resultado)
    resposta = client.get(f"/equipes/{b['id']}/resultado", headers=com_token(a["lider"]))
    assert resposta.status_code == 403
    inexistente = client.get(
        "/equipes/00000000-0000-0000-0000-000000000000/resultado",
        headers=com_token(a["lider"]),
    )
    assert inexistente.status_code == 404
    assert client.get(f"/equipes/{b['id']}/resultado").status_code == 401
