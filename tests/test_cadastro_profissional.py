"""RF01: cadastro público de profissionais, além de estudantes, na edição escolhida."""

import pytest

from tests.test_auth import cadastrar

PROFISSIONAL = {
    "tipo": "PROFISSIONAL",
    "instituicao": None,
    "curso": None,
    "periodo": None,
    "organizacao": "Açaí Labs",
    "cargo": "Desenvolvedora",
}


def test_profissional_se_cadastra_com_organizacao_e_cargo(
    client, sql, hackathon_aberto, novo_email
):
    email = novo_email()

    resposta = cadastrar(client, email, hackathon_id=str(hackathon_aberto), **PROFISSIONAL)

    assert resposta.status_code == 201, resposta.text
    usuario = sql(
        "SELECT id, situacao_conta, instituicao, curso, periodo FROM usuarios WHERE email = :e",
        e=email,
    )[0]
    assert usuario["situacao_conta"] == "PENDENTE"
    assert (usuario["instituicao"], usuario["curso"], usuario["periodo"]) == (None, None, None)
    # Organização e cargo pertencem à edição: viram a autodeclaração dele nela
    declaracao = sql(
        "SELECT id, hackathon_id, tipo, organizacao, cargo FROM autodeclaracoes_vinculo"
        " WHERE usuario_id = :u",
        u=usuario["id"],
    )
    assert len(declaracao) == 1
    assert declaracao[0]["hackathon_id"] == hackathon_aberto
    assert declaracao[0]["tipo"] == "PROFISSIONAL"
    assert (declaracao[0]["organizacao"], declaracao[0]["cargo"]) == ("Açaí Labs", "Desenvolvedora")
    # O comprovante inicial é profissional e sustenta essa declaração
    comprovante = sql(
        "SELECT hackathon_id, tipo_vinculo, autodeclaracao_id, status"
        " FROM comprovantes_vinculo WHERE usuario_id = :u",
        u=usuario["id"],
    )
    assert comprovante == [
        {
            "hackathon_id": hackathon_aberto,
            "tipo_vinculo": "PROFISSIONAL",
            "autodeclaracao_id": declaracao[0]["id"],
            "status": "PENDENTE",
        }
    ]


def test_estudante_continua_como_antes(client, sql, hackathon_aberto, novo_email):
    """Sem `tipo`, vale ESTUDANTE: dados na conta, comprovante acadêmico e nenhuma declaração."""
    email = novo_email()

    assert cadastrar(client, email, hackathon_id=str(hackathon_aberto)).status_code == 201

    usuario = sql("SELECT id, instituicao FROM usuarios WHERE email = :e", e=email)[0]
    assert usuario["instituicao"] == "UFPA"
    comprovante = sql(
        "SELECT tipo_vinculo, autodeclaracao_id FROM comprovantes_vinculo WHERE usuario_id = :u",
        u=usuario["id"],
    )
    assert comprovante == [{"tipo_vinculo": "ESTUDANTE", "autodeclaracao_id": None}]
    assert not sql("SELECT 1 FROM autodeclaracoes_vinculo WHERE usuario_id = :u", u=usuario["id"])


@pytest.mark.parametrize(
    "mudancas",
    [
        # Profissional sem organização ou cargo
        {**PROFISSIONAL, "organizacao": None},
        {**PROFISSIONAL, "cargo": None},
        # Profissional com campos de estudante
        {**PROFISSIONAL, "curso": "Sistemas"},
        # Estudante sem curso ou com campos de profissional
        {"curso": None},
        {"cargo": "Estagiária"},
        # Tipo desconhecido
        {"tipo": "MISTO"},
    ],
)
def test_campos_do_tipo_errados_dao_422(client, sql, hackathon_aberto, novo_email, mudancas):
    email = novo_email()

    resposta = cadastrar(client, email, hackathon_id=str(hackathon_aberto), **mudancas)

    assert resposta.status_code == 422
    assert not sql("SELECT 1 FROM usuarios WHERE email = :e", e=email)


def test_falha_no_cadastro_do_profissional_nao_deixa_declaracao(
    client, sql, hackathon_aberto, novo_email
):
    """E-mail repetido: nada da segunda tentativa fica no banco (rollback da transação)."""
    email = novo_email()
    assert (
        cadastrar(client, email, hackathon_id=str(hackathon_aberto), **PROFISSIONAL).status_code
        == 201
    )

    resposta = cadastrar(client, email.upper(), hackathon_id=str(hackathon_aberto), **PROFISSIONAL)

    assert resposta.status_code == 409
    total = sql(
        "SELECT count(*) AS n FROM autodeclaracoes_vinculo a JOIN usuarios u ON u.id = a.usuario_id"
        " WHERE lower(u.email) = lower(:e)",
        e=email,
    )[0]["n"]
    assert total == 1
