"""Cadastro, edição e exclusão de hackathons pelo Organizador ou DEV."""

from uuid import uuid4

import pytest

from tests.test_convites import com_token

HACKATHON = {
    "nome": "Hackathon de teste",
    "tema": "Cidades inteligentes",
    "data_inicio": "2099-12-01T09:00:00Z",
    "data_fim": "2099-12-03T18:00:00Z",
    "inscricoes_inicio": "2099-11-01T00:00:00Z",
    "inscricoes_fim": "2099-11-20T23:59:00Z",
    "homologacao_fim": "2099-11-23T23:59:00Z",
    "propostas_inicio": "2099-11-01T00:00:00Z",
    "propostas_fim": "2099-11-25T23:59:00Z",
}


class CenarioHackathons:
    def __init__(self, sql, usuario_no_banco):
        self.sql = sql
        self.usuario_no_banco = usuario_no_banco
        self.organizador = usuario_no_banco(papel="ORGANIZADOR")
        self.dev = usuario_no_banco(papel="DEV")
        self.ids: list = []

    def cadastrar(self, client, quem=None, **campos):
        resposta = client.post(
            "/admin/hackathons",
            json={**HACKATHON, **campos},
            headers=com_token((quem or self.organizador)["id"]),
        )
        if resposta.status_code == 201:
            self.ids.append(resposta.json()["id"])
        return resposta

    def cadastrado(self, client, **campos) -> dict:
        resposta = self.cadastrar(client, **campos)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    def editar(self, client, hackathon_id, dados, quem=None):
        return client.patch(
            f"/admin/hackathons/{hackathon_id}",
            json=dados,
            headers=com_token((quem or self.organizador)["id"]),
        )

    def excluir(self, client, hackathon_id, quem=None):
        return client.delete(
            f"/admin/hackathons/{hackathon_id}",
            headers=com_token((quem or self.organizador)["id"]),
        )

    def limpar(self):
        for id_ in self.ids:
            self.sql("DELETE FROM equipes WHERE hackathon_id = :h", h=id_)
            self.sql("DELETE FROM hackathon WHERE id = :h", h=id_)


@pytest.fixture
def hackathons(sql, usuario_no_banco):
    cenario = CenarioHackathons(sql, usuario_no_banco)
    try:
        yield cenario
    finally:
        cenario.limpar()


@pytest.mark.parametrize("perfil", ["organizador", "dev"])
def test_organizador_e_dev_cadastram_hackathon(client, hackathons, perfil):
    resposta = hackathons.cadastrar(client, quem=getattr(hackathons, perfil))

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["nome"] == HACKATHON["nome"]
    assert corpo["status"] == "INSCRICOES"
    assert (corpo["min_integrantes"], corpo["max_integrantes"]) == (3, 5)
    linha = hackathons.sql("SELECT * FROM hackathon WHERE id = :h", h=corpo["id"])[0]
    assert linha["nome"] == HACKATHON["nome"]
    assert linha["inscricoes_fim"].isoformat() == "2099-11-20T23:59:00"


def test_datas_com_fuso_sao_gravadas_em_utc(client, hackathons):
    corpo = hackathons.cadastrado(client, data_inicio="2099-12-01T09:00:00-03:00")
    linha = hackathons.sql("SELECT data_inicio FROM hackathon WHERE id = :h", h=corpo["id"])[0]
    assert linha["data_inicio"].isoformat() == "2099-12-01T12:00:00"


def test_cadastro_so_com_nome(client, hackathons):
    resposta = hackathons.cadastrar(
        client,
        **{campo: None for campo in HACKATHON if campo != "nome"},
    )
    assert resposta.status_code == 201, resposta.text


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_CIENTIFICO"])
def test_outros_perfis_nao_cadastram_hackathon(client, hackathons, papel):
    quem = hackathons.usuario_no_banco(papel=papel)
    assert hackathons.cadastrar(client, quem=quem).status_code == 403


def test_cadastro_exige_token(client):
    assert client.post("/admin/hackathons", json=HACKATHON).status_code == 401


@pytest.mark.parametrize(
    "campos",
    [
        {"data_fim": "2099-11-30T00:00:00Z"},
        {"inscricoes_fim": "2099-11-01T00:00:00Z"},
        {"homologacao_fim": "2099-11-19T00:00:00Z"},
        {"propostas_fim": "2099-10-01T00:00:00Z"},
        {"min_integrantes": 6},
        {"avaliadores_por_proposta": 4},
        {"status": "INVALIDO"},
    ],
    ids=[
        "fim-antes-do-inicio",
        "inscricoes-sem-duracao",
        "homologacao-antes-das-inscricoes",
        "propostas-fora-de-ordem",
        "min-maior-que-max",
        "avaliadores-fora-da-faixa",
        "status-invalido",
    ],
)
def test_cadastro_valida_campos(client, hackathons, campos):
    assert hackathons.cadastrar(client, **campos).status_code == 422


def test_edicao_altera_apenas_os_campos_enviados(client, hackathons):
    hackathon = hackathons.cadastrado(client)

    resposta = hackathons.editar(
        client, hackathon["id"], {"nome": "Novo nome", "status": "ATIVO", "tema": None}
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["nome"] == "Novo nome"
    assert corpo["status"] == "ATIVO"
    assert corpo["tema"] is None
    assert corpo["data_inicio"].startswith("2099-12-01T09:00:00")


def test_edicao_valida_com_os_valores_ja_gravados(client, hackathons):
    hackathon = hackathons.cadastrado(client)

    # max_integrantes sozinho é válido, mas fica menor que o min_integrantes gravado (3)
    assert hackathons.editar(client, hackathon["id"], {"max_integrantes": 2}).status_code == 422
    # inscricoes_inicio depois do inscricoes_fim gravado
    resposta = hackathons.editar(
        client, hackathon["id"], {"inscricoes_inicio": "2099-11-21T00:00:00Z"}
    )
    assert resposta.status_code == 422

    linha = hackathons.sql("SELECT * FROM hackathon WHERE id = :h", h=hackathon["id"])[0]
    assert linha["max_integrantes"] == 5


@pytest.mark.parametrize("campo", ["status", "min_integrantes", "max_integrantes"])
def test_edicao_nao_aceita_null_em_campo_obrigatorio(client, hackathons, campo):
    hackathon = hackathons.cadastrado(client)
    assert hackathons.editar(client, hackathon["id"], {campo: None}).status_code == 422


def test_edicao_de_hackathon_inexistente(client, hackathons):
    assert hackathons.editar(client, uuid4(), {"nome": "x"}).status_code == 404


def test_participante_nao_edita_nem_exclui(client, hackathons):
    hackathon = hackathons.cadastrado(client)
    participante = hackathons.usuario_no_banco()

    assert (
        hackathons.editar(client, hackathon["id"], {"nome": "x"}, participante).status_code == 403
    )
    assert hackathons.excluir(client, hackathon["id"], participante).status_code == 403


@pytest.mark.parametrize("perfil", ["organizador", "dev"])
def test_exclui_hackathon_sem_dados(client, hackathons, perfil):
    hackathon = hackathons.cadastrado(client)

    resposta = hackathons.excluir(client, hackathon["id"], quem=getattr(hackathons, perfil))

    assert resposta.status_code == 204
    assert hackathons.sql("SELECT 1 FROM hackathon WHERE id = :h", h=hackathon["id"]) == []


def test_nao_exclui_hackathon_com_dados_ligados(client, hackathons):
    hackathon = hackathons.cadastrado(client)
    hackathons.sql(
        "INSERT INTO equipes (hackathon_id, nome) VALUES (:h, 'Equipe')", h=hackathon["id"]
    )

    resposta = hackathons.excluir(client, hackathon["id"])

    assert resposta.status_code == 409
    assert "CANCELADO" in resposta.json()["detail"]
    assert hackathons.sql("SELECT 1 FROM hackathon WHERE id = :h", h=hackathon["id"]) != []


def test_exclusao_de_hackathon_inexistente(client, hackathons):
    assert hackathons.excluir(client, uuid4()).status_code == 404
