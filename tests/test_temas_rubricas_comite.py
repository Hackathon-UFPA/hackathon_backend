"""BE-S5-08: catálogo público de temas, Comitê Científico gerenciando temas e rubricas e
uma rubrica por fase (PROPOSTA e PROJETO_FINAL) com janelas de publicação próprias."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from tests.conftest import executar_sql
from tests.test_avaliacao_cientifica import CenarioCientifico
from tests.test_convites import com_token
from tests.test_rubrica import CenarioRubrica, criterio, criterios_completos
from tests.test_temas import CenarioTemas


@pytest.fixture
def temas(sql, usuario_no_banco, novo_email):
    cenario = CenarioTemas(sql, usuario_no_banco, novo_email)
    try:
        yield cenario
    finally:
        cenario.limpar()


@pytest.fixture
def rubrica(sql, usuario_no_banco, novo_email):
    cenario = CenarioRubrica(sql, usuario_no_banco, novo_email)
    try:
        yield cenario
    finally:
        cenario.limpar()


@pytest.fixture
def cientifica(sql, usuario_no_banco):
    cenario = CenarioCientifico(sql, usuario_no_banco)
    try:
        yield cenario
    finally:
        cenario.limpar()


# --- Catálogo público de temas (RF10, RF17) ---


def test_catalogo_de_temas_ativos_e_publico(client, temas):
    ativo = temas.cadastrado(client, titulo="Ativo")
    temas.cadastrado(client, titulo="Inativo", ativo=False)

    resposta = client.get(f"/hackathons/{temas.hackathon_id}/temas")

    assert resposta.status_code == 200, resposta.text
    assert [t["id"] for t in resposta.json()] == [ativo["id"]]
    detalhe = client.get(f"/temas/{ativo['id']}")
    assert detalhe.status_code == 200
    assert detalhe.json()["titulo"] == "Ativo"


def test_tema_desativado_nao_aparece_para_visitante(client, temas):
    inativo = temas.cadastrado(client, ativo=False)
    assert client.get(f"/temas/{inativo['id']}").status_code == 404


def test_catalogo_de_edicao_inexistente(client):
    assert client.get(f"/hackathons/{uuid4()}/temas").status_code == 404


def test_inativos_exigem_token(client, temas):
    resposta = client.get(
        f"/hackathons/{temas.hackathon_id}/temas", params={"incluir_inativos": "true"}
    )
    assert resposta.status_code == 401


@pytest.mark.parametrize("rota", ["lista", "detalhe"])
def test_token_invalido_no_catalogo_retorna_401(client, temas, rota):
    tema = temas.cadastrado(client)
    url = f"/hackathons/{temas.hackathon_id}/temas" if rota == "lista" else f"/temas/{tema['id']}"
    resposta = client.get(url, headers={"Authorization": "Bearer token-invalido"})
    assert resposta.status_code == 401


@pytest.mark.parametrize("papel", ["COMITE_TECNICO", "PARTICIPANTE"])
def test_outros_perfis_nao_pedem_inativos(client, temas, papel):
    quem = temas.usuario_no_banco(papel=papel)
    assert temas.listar(client, quem=quem, incluir_inativos="true").status_code == 403


def test_comite_pendente_nao_pede_inativos(client, temas):
    quem = temas.usuario_no_banco(papel="COMITE_CIENTIFICO", situacao_conta="PENDENTE")
    assert temas.listar(client, quem=quem, incluir_inativos="true").status_code == 403


# --- Comitê Científico gerencia temas (RF15) ---


def test_comite_gerencia_temas(client, temas):
    tema = temas.cadastrado(client, quem=temas.comite)
    inativo = temas.cadastrado(client, quem=temas.comite, titulo="Outro", ativo=False)

    editado = temas.editar(client, tema["id"], {"titulo": "Queimadas"}, quem=temas.comite)
    todos = temas.listar(client, quem=temas.comite, incluir_inativos="true")
    detalhe = client.get(f"/temas/{inativo['id']}", headers=com_token(temas.comite["id"]))
    excluido = temas.excluir(client, inativo["id"], quem=temas.comite)

    assert editado.status_code == 200
    assert editado.json()["titulo"] == "Queimadas"
    assert {t["titulo"] for t in todos.json()} == {"Queimadas", "Outro"}
    assert detalhe.status_code == 200
    assert excluido.status_code == 204


@pytest.mark.parametrize("acao", ["editar", "excluir"])
def test_escrita_de_tema_exige_token(client, temas, acao):
    tema = temas.cadastrado(client)
    if acao == "editar":
        resposta = client.patch(f"/temas/{tema['id']}", json={"ativo": False})
    else:
        resposta = client.delete(f"/temas/{tema['id']}")
    assert resposta.status_code == 401


# --- Rubrica: permissões (RF16) ---


def test_comite_monta_e_publica_rubrica(client, rubrica):
    comite = rubrica.usuario_no_banco(papel="COMITE_CIENTIFICO")

    assert rubrica.salvar(client, criterios_completos(), quem=comite).status_code == 200
    assert rubrica.rascunho(client, quem=comite).status_code == 200
    resposta = rubrica.publicar(client, quem=comite)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["fase"] == "PROPOSTA"


@pytest.mark.parametrize("fase", ["PROPOSTA", "PROJETO_FINAL"])
def test_rubrica_exige_token(client, rubrica, fase):
    url, params = rubrica.url, {"fase": fase}
    assert client.put(url, json={"criterios": []}, params=params).status_code == 401
    assert client.post(f"{url}/publicar", params=params).status_code == 401
    assert client.get(f"{url}/rascunho", params=params).status_code == 401


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "COMITE_TECNICO"])
def test_outros_perfis_nao_editam_rubrica_do_projeto_final(client, rubrica, papel):
    quem = rubrica.usuario_no_banco(papel=papel)
    params = {"fase": "PROJETO_FINAL"}
    cabecalho = com_token(quem["id"])
    corpo = {"criterios": criterios_completos()}
    assert client.put(rubrica.url, json=corpo, params=params, headers=cabecalho).status_code == 403
    publicar = client.post(f"{rubrica.url}/publicar", params=params, headers=cabecalho)
    assert publicar.status_code == 403


# --- Rubrica: uma por fase ---


def salvar_fase(client, rubrica, fase, criterios, quem=None):
    return client.put(
        rubrica.url,
        params={"fase": fase},
        json={"criterios": criterios},
        headers=com_token((quem or rubrica.organizador)["id"]),
    )


def publicar_fase(client, rubrica, fase):
    return client.post(
        f"{rubrica.url}/publicar",
        params={"fase": fase},
        headers=com_token(rubrica.organizador["id"]),
    )


def rascunho_fase(client, rubrica, fase):
    return client.get(
        f"{rubrica.url}/rascunho",
        params={"fase": fase},
        headers=com_token(rubrica.organizador["id"]),
    )


def criterios_do_projeto_final():
    itens = criterios_completos()
    itens[0]["peso"], itens[1]["peso"] = "10", "40"  # 10 + 40 + 25 + 25
    itens.append(criterio("Qualidade do código", 0.01))
    itens[-2]["peso"] = "24.99"
    return itens


def test_fases_tem_criterios_e_pesos_independentes(client, rubrica):
    proposta = salvar_fase(client, rubrica, "PROPOSTA", criterios_completos())
    final = salvar_fase(client, rubrica, "PROJETO_FINAL", criterios_do_projeto_final())

    assert proposta.status_code == final.status_code == 200, final.text
    assert proposta.json()["id"] != final.json()["id"]
    assert final.json()["fase"] == "PROJETO_FINAL"
    pesos_proposta = [
        c["peso"] for c in rascunho_fase(client, rubrica, "PROPOSTA").json()["criterios"]
    ]
    pesos_final = [
        c["peso"] for c in rascunho_fase(client, rubrica, "PROJETO_FINAL").json()["criterios"]
    ]
    assert pesos_proposta == ["25.00", "25.00", "25.00", "25.00"]
    assert pesos_final == ["10.00", "40.00", "25.00", "24.99", "0.01"]


def test_rubrica_sem_fase_e_a_da_proposta(client, rubrica):
    """Clientes que não mandam `fase` continuam usando a rubrica que já existia."""
    rubrica.publicada(client)
    rascunho = rascunho_fase(client, rubrica, "PROPOSTA").json()

    assert rascunho["fase"] == "PROPOSTA"
    assert client.get(rubrica.url).json()["id"] == rascunho["id"]
    assert client.get(rubrica.url, params={"fase": "PROJETO_FINAL"}).status_code == 404
    assert rascunho_fase(client, rubrica, "PROJETO_FINAL").status_code == 404


def test_publicar_uma_fase_nao_publica_nem_trava_a_outra(client, rubrica):
    rubrica.publicada(client)

    salvo = salvar_fase(client, rubrica, "PROJETO_FINAL", criterios_completos())
    publicado = publicar_fase(client, rubrica, "PROJETO_FINAL")

    assert salvo.status_code == 200
    assert publicado.status_code == 200, publicado.text
    publica = client.get(rubrica.url, params={"fase": "PROJETO_FINAL"})
    assert publica.status_code == 200
    assert publica.json()["fase"] == "PROJETO_FINAL"
    # A da proposta continua imutável.
    assert salvar_fase(client, rubrica, "PROPOSTA", [criterio("Novo", 100)]).status_code == 409


def test_fase_invalida(client, rubrica):
    resposta = client.get(rubrica.url, params={"fase": "FINAL"})
    assert resposta.status_code == 422


def test_projeto_final_exige_minimos_da_rn10(client, rubrica):
    salvar_fase(client, rubrica, "PROJETO_FINAL", [criterio("Qualquer", 100)])

    resposta = publicar_fase(client, rubrica, "PROJETO_FINAL")

    assert resposta.status_code == 422
    assert "RN10" in resposta.json()["detail"]


# --- Rubrica: janela de publicação por fase ---


def test_projeto_final_pode_ser_publicado_depois_das_inscricoes(client, rubrica):
    rubrica.inscricoes_inicio(-1)
    salvar_fase(client, rubrica, "PROPOSTA", criterios_completos())
    salvar_fase(client, rubrica, "PROJETO_FINAL", criterios_completos())

    assert publicar_fase(client, rubrica, "PROPOSTA").status_code == 409
    assert publicar_fase(client, rubrica, "PROJETO_FINAL").status_code == 200


def test_projeto_final_nao_publica_depois_do_resultado_homologado(client, rubrica):
    salvar_fase(client, rubrica, "PROJETO_FINAL", criterios_completos())
    rubrica.sql(
        "INSERT INTO homologacoes_resultado"
        " (hackathon_id, homologado_por, total_propostas, total_aprovadas)"
        " VALUES (:h, :u, 0, 0)",
        h=rubrica.hackathon_id,
        u=rubrica.organizador["id"],
    )
    try:
        resposta = publicar_fase(client, rubrica, "PROJETO_FINAL")
    finally:
        rubrica.sql(
            "DELETE FROM homologacoes_resultado WHERE hackathon_id = :h", h=rubrica.hackathon_id
        )

    assert resposta.status_code == 409
    assert "homologação" in resposta.json()["detail"]


# --- Banco: compatibilidade e integridade ---


def test_rubrica_criada_sem_fase_fica_na_proposta(client, rubrica):
    """Mesmo efeito da migration sobre a rubrica que já existia."""
    linha = executar_sql(
        "INSERT INTO rubricas (hackathon_id) VALUES (:h) RETURNING fase", h=rubrica.hackathon_id
    )[0]
    assert linha["fase"] == "PROPOSTA"


def test_banco_permite_uma_rubrica_por_fase(client, rubrica):
    executar_sql(
        "INSERT INTO rubricas (hackathon_id, fase) VALUES (:h, 'PROPOSTA'), (:h, 'PROJETO_FINAL')",
        h=rubrica.hackathon_id,
    )
    with pytest.raises(IntegrityError, match="uq_rubricas_hackathon_fase"):
        executar_sql(
            "INSERT INTO rubricas (hackathon_id, fase) VALUES (:h, 'PROJETO_FINAL')",
            h=rubrica.hackathon_id,
        )


def test_avaliacao_cientifica_nao_usa_rubrica_do_projeto_final(client, cientifica):
    assert cientifica.enviar(client, cientifica.completo()).status_code == 200
    final = executar_sql(
        "INSERT INTO rubricas (hackathon_id, fase) VALUES (:h, 'PROJETO_FINAL') RETURNING id",
        h=cientifica.hackathon_id,
    )[0]["id"]

    with pytest.raises(IntegrityError, match="avaliacao_rubrica_fase"):
        executar_sql(
            "UPDATE avaliacoes SET rubrica_id = :r WHERE submissao_id = :s",
            r=final,
            s=cientifica.proposta_id,
        )
    # A avaliação feita com a rubrica da proposta continua intacta.
    assert cientifica.registros()[0]["rubrica_id"] == cientifica.rubrica_id
