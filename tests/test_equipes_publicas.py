"""Lista pública das equipes de um hackathon (página do hackathon)."""

from uuid import uuid4

import pytest


@pytest.fixture
def edicao(sql, usuario_no_banco):
    """Hackathon com uma equipe homologada (3 integrantes), uma aguardando e uma em formação."""
    h = sql(
        "INSERT INTO hackathon (nome, status)"
        " VALUES ('Equipes públicas', 'INSCRICOES') RETURNING id"
    )[0]["id"]
    equipes = {}
    for nome, situacao, n in [
        ("Homologada", "HOMOLOGADA", 3),
        ("Aguardando", "AGUARDANDO_HOMOLOGACAO", 3),
        (None, "EM_FORMACAO", 1),
    ]:
        e = sql(
            "INSERT INTO equipes (hackathon_id, nome, situacao, homologada_em)"
            " VALUES (:h, :n, CAST(:s AS situacao_equipe),"
            " CASE WHEN :s = 'HOMOLOGADA' THEN now() END) RETURNING id",
            h=h,
            n=nome,
            s=situacao,
        )[0]["id"]
        for _ in range(n):
            u = usuario_no_banco()
            sql(
                "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id)"
                " VALUES (:e, :u, :h)",
                e=e,
                u=u["id"],
                h=h,
            )
        equipes[situacao] = e
    try:
        yield h
    finally:
        sql("DELETE FROM membros_equipe WHERE hackathon_id = :h", h=h)
        sql("DELETE FROM equipes WHERE hackathon_id = :h", h=h)
        sql("DELETE FROM hackathon WHERE id = :h", h=h)


def test_lista_so_as_homologadas_sem_dados_pessoais(client, edicao):
    resposta = client.get(f"/hackathons/{edicao}/equipes")  # sem login

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [(e["nome"], e["integrantes"]) for e in corpo["homologadas"]] == [("Homologada", 3)]
    assert corpo["homologadas"][0]["homologada_em"] is not None
    assert set(corpo["homologadas"][0]) == {"nome", "integrantes", "homologada_em"}
    assert corpo["total_homologadas"] == 1
    assert corpo["total_aguardando_homologacao"] == 1
    assert corpo["total_em_formacao"] == 1


def test_rascunho_e_inexistente_dao_404(client, edicao, sql):
    sql("UPDATE hackathon SET status = 'RASCUNHO' WHERE id = :h", h=edicao)

    assert client.get(f"/hackathons/{edicao}/equipes").status_code == 404
    assert client.get(f"/hackathons/{uuid4()}/equipes").status_code == 404
