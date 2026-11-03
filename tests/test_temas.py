"""BE-S4-06: cadastro, edição, ativação e exclusão de temas (RF15, RN04)."""

from uuid import uuid4

import pytest

from tests.test_convites import com_token
from tests.test_submissoes import CenarioSubmissoes

TEMA = {
    "titulo": "Monitoramento do desmatamento",
    "descricao": "Soluções para acompanhar a perda de floresta",
    "contexto": "Dados do INPE",
    "ods": [15, 13, 15],
}


class CenarioTemas(CenarioSubmissoes):
    def __init__(self, *args):
        super().__init__(*args)
        self.organizador = self.usuario_no_banco(papel="ORGANIZADOR")
        self.dev = self.usuario_no_banco(papel="DEV")
        # O líder da equipe é um participante comum
        self.participante = self.lider

    def cadastrar(self, client, quem=None, hackathon_id=None, **campos):
        return client.post(
            f"/hackathons/{hackathon_id or self.hackathon_id}/temas",
            json={**TEMA, **campos},
            headers=com_token((quem or self.organizador)["id"]),
        )

    def cadastrado(self, client, **campos) -> dict:
        resposta = self.cadastrar(client, **campos)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    def listar(self, client, quem=None, **params):
        return client.get(
            f"/hackathons/{self.hackathon_id}/temas",
            params=params,
            headers=com_token((quem or self.participante)["id"]),
        )

    def editar(self, client, tema_id, dados, quem=None):
        return client.patch(
            f"/temas/{tema_id}", json=dados, headers=com_token((quem or self.organizador)["id"])
        )

    def excluir(self, client, tema_id, quem=None):
        return client.delete(
            f"/temas/{tema_id}", headers=com_token((quem or self.organizador)["id"])
        )


@pytest.fixture
def temas(sql, usuario_no_banco, novo_email):
    cenario = CenarioTemas(sql, usuario_no_banco, novo_email)
    try:
        yield cenario
    finally:
        cenario.limpar()


@pytest.mark.parametrize("perfil", ["organizador", "dev"])
def test_organizador_e_dev_cadastram_tema(client, temas, perfil):
    resposta = temas.cadastrar(client, quem=getattr(temas, perfil))

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["hackathon_id"] == str(temas.hackathon_id)
    assert corpo["titulo"] == TEMA["titulo"]
    assert corpo["descricao"] == TEMA["descricao"]
    assert corpo["ods"] == [13, 15]
    assert corpo["ativo"] is True
    assert corpo["criado_em"] is not None
    linha = temas.sql("SELECT * FROM temas WHERE id = :t", t=corpo["id"])[0]
    assert linha["ods"] == [13, 15]


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_CIENTIFICO"])
def test_outros_perfis_nao_cadastram_tema(client, temas, papel):
    resposta = temas.cadastrar(client, quem=temas.usuario_no_banco(papel=papel))
    assert resposta.status_code == 403


def test_cadastro_exige_token(client, temas):
    resposta = client.post(f"/hackathons/{temas.hackathon_id}/temas", json=TEMA)
    assert resposta.status_code == 401


@pytest.mark.parametrize(
    "campos",
    [
        {"titulo": "   "},
        {"descricao": ""},
        {"descricao": None},
        {"ods": []},
        {"ods": [0]},
        {"ods": [18]},
    ],
    ids=["titulo-vazio", "descricao-vazia", "descricao-nula", "sem-ods", "ods-0", "ods-18"],
)
def test_tema_exige_titulo_descricao_e_ods(client, temas, campos):
    assert temas.cadastrar(client, **campos).status_code == 422


def test_titulo_repetido_na_mesma_edicao(client, temas):
    temas.cadastrado(client)
    assert temas.cadastrar(client).status_code == 409

    # Em outra edição o mesmo título é permitido
    outro = temas.criar_hackathon()
    assert temas.cadastrar(client, hackathon_id=outro).status_code == 201


def test_cadastro_em_hackathon_inexistente(client, temas):
    assert temas.cadastrar(client, hackathon_id=uuid4()).status_code == 404


def test_edicao_altera_apenas_os_campos_enviados(client, temas):
    tema = temas.cadastrado(client)

    resposta = temas.editar(client, tema["id"], {"titulo": "Queimadas", "contexto": None})

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["titulo"] == "Queimadas"
    assert corpo["contexto"] is None
    assert corpo["descricao"] == TEMA["descricao"]
    assert corpo["ods"] == [13, 15]
    assert corpo["atualizado_em"] is not None


@pytest.mark.parametrize("campo", ["titulo", "descricao", "ods", "ativo"])
def test_edicao_nao_aceita_null_em_campo_obrigatorio(client, temas, campo):
    tema = temas.cadastrado(client)
    assert temas.editar(client, tema["id"], {campo: None}).status_code == 422


def test_edicao_com_titulo_de_outro_tema(client, temas):
    temas.cadastrado(client, titulo="Água")
    tema = temas.cadastrado(client, titulo="Energia")
    assert temas.editar(client, tema["id"], {"titulo": "Água"}).status_code == 409


def test_participante_nao_edita_tema(client, temas):
    tema = temas.cadastrado(client)
    resposta = temas.editar(client, tema["id"], {"ativo": False}, quem=temas.participante)
    assert resposta.status_code == 403


def test_editar_tema_inexistente(client, temas):
    assert temas.editar(client, uuid4(), {"ativo": False}).status_code == 404


def test_tema_desativado_some_da_listagem_de_participantes(client, temas):
    ativo = temas.cadastrado(client, titulo="Ativo")
    inativo = temas.cadastrado(client, titulo="Inativo")
    assert temas.editar(client, inativo["id"], {"ativo": False}).json()["ativo"] is False

    resposta = temas.listar(client)

    assert resposta.status_code == 200
    assert [t["id"] for t in resposta.json()] == [ativo["id"]]
    detalhe = client.get(f"/temas/{inativo['id']}", headers=com_token(temas.participante["id"]))
    assert detalhe.status_code == 404


def test_organizador_lista_inativos_quando_pede(client, temas):
    temas.cadastrado(client, titulo="A")
    inativo = temas.cadastrado(client, titulo="B", ativo=False)

    padrao = temas.listar(client, quem=temas.organizador)
    todos = temas.listar(client, quem=temas.organizador, incluir_inativos="true")

    assert [t["titulo"] for t in padrao.json()] == ["A"]
    assert [t["titulo"] for t in todos.json()] == ["A", "B"]
    detalhe = client.get(f"/temas/{inativo['id']}", headers=com_token(temas.organizador["id"]))
    assert detalhe.status_code == 200


def test_participante_nao_pede_inativos(client, temas):
    assert temas.listar(client, incluir_inativos="true").status_code == 403


def test_listagem_de_outra_edicao_nao_mistura(client, temas):
    outro = temas.criar_hackathon()
    temas.cadastrado(client, hackathon_id=outro)
    assert temas.listar(client).json() == []


def test_reativar_tema(client, temas):
    tema = temas.cadastrado(client, ativo=False)
    assert temas.editar(client, tema["id"], {"ativo": True}).status_code == 200
    assert [t["id"] for t in temas.listar(client).json()] == [tema["id"]]


def test_tema_desativado_nao_pode_ser_escolhido_na_proposta(client, temas):
    tema = temas.cadastrado(client, ativo=False)
    resposta = temas.requisitar(client, dados={"tema_id": tema["id"]})
    assert resposta.status_code == 409


def test_excluir_tema_sem_propostas(client, temas):
    tema = temas.cadastrado(client)

    assert temas.excluir(client, tema["id"]).status_code == 204
    assert temas.sql("SELECT 1 FROM temas WHERE id = :t", t=tema["id"]) == []
    assert temas.excluir(client, tema["id"]).status_code == 404


@pytest.mark.parametrize("enviada", [False, True], ids=["rascunho", "enviada"])
def test_nao_exclui_tema_com_propostas(client, temas, enviada):
    tema = temas.cadastrado(client)
    assert temas.requisitar(client, dados={"tema_id": tema["id"]}).status_code == 201
    if enviada:
        temas.sql(
            "UPDATE submissoes SET status = 'ENVIADA', titulo = 'T', descricao = 'D',"
            " ods = '{1}', bases_dados = 'IBGE', enviado_em = now() WHERE equipe_id = :e",
            e=temas.equipe_id,
        )

    resposta = temas.excluir(client, tema["id"])

    assert resposta.status_code == 409
    assert "RN04" in resposta.json()["detail"]
    assert temas.sql("SELECT 1 FROM temas WHERE id = :t", t=tema["id"]) != []


def test_participante_nao_exclui_tema(client, temas):
    tema = temas.cadastrado(client)
    assert temas.excluir(client, tema["id"], quem=temas.participante).status_code == 403
