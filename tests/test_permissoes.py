"""
Identificação por token, perfis e permissões (RF06) e cadastro de usuários por perfil (RF07, RF08).

Estes testes gravam no banco de verdade; as fixtures de conftest.py apagam os dados no final.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.const.config import settings
from app.const.enums import PapelUsuario
from app.security.permissoes import perfis_cadastraveis, pode_cadastrar
from app.security.token import ALGORITMO, criar_token

SENHA = "segredo123"

PAPEIS = [papel.value for papel in PapelUsuario]
PAPEIS_SEM_ACESSO = ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO"]


def com_token(usuario_id) -> dict:
    return {"Authorization": f"Bearer {criar_token(usuario_id)}"}


def dados_de_usuario(email: str, papel: str, **extras) -> dict:
    return {"email": email, "papel": papel, "nome": "Fulano de Tal", "senha": SENHA, **extras}


def cadastrar_usuario(client, quem, email: str, papel: str, **extras):
    return client.post(
        "/admin/usuarios",
        json=dados_de_usuario(email, papel, **extras),
        headers=com_token(quem["id"]),
    )


# --- Identificação (GET /auth/me) ---


def test_me_devolve_os_dados_de_quem_esta_logado(client, usuario_no_banco):
    usuario = usuario_no_banco(papel="MENTOR")

    resposta = client.get("/auth/me", headers=com_token(usuario["id"]))

    assert resposta.status_code == 200
    assert resposta.json()["email"] == usuario["email"]
    assert resposta.json()["papel"] == "MENTOR"
    assert "senha_hash" not in resposta.json()


def test_conta_pendente_consulta_os_proprios_dados(client, usuario_no_banco):
    usuario = usuario_no_banco(situacao_conta="PENDENTE")

    resposta = client.get("/auth/me", headers=com_token(usuario["id"]))

    assert resposta.status_code == 200
    assert resposta.json()["situacao_conta"] == "PENDENTE"


def test_fluxo_completo_login_e_consulta(client, usuario_no_banco):
    usuario = usuario_no_banco()

    token = client.post("/auth/login", json={"email": usuario["email"], "senha": SENHA}).json()[
        "access_token"
    ]
    resposta = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resposta.status_code == 200
    assert resposta.json()["email"] == usuario["email"]


def assinar(claims: dict) -> dict:
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm=ALGORITMO)
    return {"Authorization": f"Bearer {token}"}


def test_sem_token(client):
    resposta = client.get("/auth/me")

    assert resposta.status_code == 401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "cabecalho",
    [
        {"Authorization": "Bearer isto-nao-e-um-token"},
        {"Authorization": "Basic dXN1YXJpbzpzZW5oYQ=="},
        {"Authorization": "Bearer "},
    ],
)
def test_token_invalido(client, cabecalho):
    assert client.get("/auth/me", headers=cabecalho).status_code == 401


def test_token_vencido(client, usuario_no_banco):
    usuario = usuario_no_banco()
    vencido = datetime.now(UTC) - timedelta(seconds=1)

    cabecalho = assinar({"sub": str(usuario["id"]), "exp": vencido})

    assert client.get("/auth/me", headers=cabecalho).status_code == 401


def test_token_adulterado(client, usuario_no_banco):
    usuario = usuario_no_banco()
    cabecalho, corpo, assinatura = criar_token(usuario["id"]).split(".")

    adulterado = {"Authorization": f"Bearer {cabecalho}.{corpo[::-1]}.{assinatura}"}

    assert client.get("/auth/me", headers=adulterado).status_code == 401


def test_token_de_usuario_que_nao_existe(client):
    assert client.get("/auth/me", headers=com_token(uuid4())).status_code == 401


def test_token_de_conta_desativada_deixa_de_valer(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    assert client.get("/auth/me", headers=com_token(usuario["id"])).status_code == 200

    sql("UPDATE usuarios SET ativo = false WHERE id = :id", id=usuario["id"])

    assert client.get("/auth/me", headers=com_token(usuario["id"])).status_code == 401


def test_troca_de_perfil_vale_no_pedido_seguinte(client, sql, usuario_no_banco, novo_email):
    usuario = usuario_no_banco(papel="ORGANIZADOR")
    corpo = dados_de_usuario(novo_email(), "MENTOR")
    assert (
        client.post("/admin/usuarios", json=corpo, headers=com_token(usuario["id"])).status_code
        == 201
    )

    sql("UPDATE usuarios SET papel = 'PARTICIPANTE' WHERE id = :id", id=usuario["id"])
    corpo = dados_de_usuario(novo_email(), "MENTOR")

    assert (
        client.post("/admin/usuarios", json=corpo, headers=com_token(usuario["id"])).status_code
        == 403
    )


# --- Cadastro de usuários por perfil (POST /admin/usuarios) ---


def test_cadastro_de_usuario_sem_token(client, novo_email):
    corpo = dados_de_usuario(novo_email(), "MENTOR")

    assert client.post("/admin/usuarios", json=corpo).status_code == 401


@pytest.mark.parametrize("papel", PAPEIS_SEM_ACESSO)
def test_perfil_sem_permissao_nao_cadastra_usuarios(client, usuario_no_banco, novo_email, papel):
    usuario = usuario_no_banco(papel=papel)

    resposta = cadastrar_usuario(client, usuario, novo_email(), "MENTOR")

    assert resposta.status_code == 403


def test_conta_pendente_nao_cadastra_usuarios(client, usuario_no_banco, novo_email):
    organizador = usuario_no_banco(papel="ORGANIZADOR", situacao_conta="PENDENTE")

    resposta = cadastrar_usuario(client, organizador, novo_email(), "MENTOR")

    assert resposta.status_code == 403


@pytest.mark.parametrize("papel", [p for p in PAPEIS if p != "DEV"])
def test_organizador_cadastra_qualquer_perfil_de_negocio(
    client, usuario_no_banco, novo_email, papel
):
    organizador = usuario_no_banco(papel="ORGANIZADOR")
    email = novo_email()

    resposta = cadastrar_usuario(client, organizador, email, papel)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["email"] == email
    assert corpo["papel"] == papel
    assert corpo["situacao_conta"] == "ATIVA"
    assert "senha" not in corpo
    assert "senha_hash" not in corpo


def test_organizador_nao_cadastra_dev(client, usuario_no_banco, novo_email):
    organizador = usuario_no_banco(papel="ORGANIZADOR")

    assert cadastrar_usuario(client, organizador, novo_email(), "DEV").status_code == 403


@pytest.mark.parametrize("papel", ["COMITE_TECNICO", "MENTOR"])
def test_comite_cientifico_cadastra_comite_tecnico_e_mentor(
    client, usuario_no_banco, novo_email, papel
):
    comite = usuario_no_banco(papel="COMITE_CIENTIFICO")

    assert cadastrar_usuario(client, comite, novo_email(), papel).status_code == 201


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "COMITE_CIENTIFICO", "ORGANIZADOR", "DEV"])
def test_comite_cientifico_nao_cadastra_os_demais_perfis(
    client, usuario_no_banco, novo_email, papel
):
    comite = usuario_no_banco(papel="COMITE_CIENTIFICO")

    assert cadastrar_usuario(client, comite, novo_email(), papel).status_code == 403


@pytest.mark.parametrize("papel", PAPEIS)
def test_dev_acessa_a_rota_e_cadastra_qualquer_perfil(client, usuario_no_banco, novo_email, papel):
    dev = usuario_no_banco(papel="DEV")

    assert cadastrar_usuario(client, dev, novo_email(), papel).status_code == 201


def test_usuario_cadastrado_consegue_entrar(client, usuario_no_banco, novo_email):
    organizador = usuario_no_banco(papel="ORGANIZADOR")
    email = novo_email()
    cadastrar_usuario(client, organizador, email, "MENTOR")

    resposta = client.post("/auth/login", json={"email": email, "senha": SENHA})

    assert resposta.status_code == 200


def test_cadastro_de_mentor_guarda_os_dados_do_perfil(client, usuario_no_banco, novo_email):
    organizador = usuario_no_banco(papel="ORGANIZADOR")

    resposta = cadastrar_usuario(
        client,
        organizador,
        novo_email(),
        "MENTOR",
        empresa_parceira="Açaí Valley",
        area_atuacao="Ciência de dados",
        max_equipes=2,
    )

    corpo = resposta.json()
    assert corpo["empresa_parceira"] == "Açaí Valley"
    assert corpo["area_atuacao"] == "Ciência de dados"
    assert corpo["max_equipes"] == 2


def test_cadastro_de_usuario_com_email_repetido(client, usuario_no_banco, novo_email):
    organizador = usuario_no_banco(papel="ORGANIZADOR")
    email = novo_email()
    cadastrar_usuario(client, organizador, email, "MENTOR")

    assert cadastrar_usuario(client, organizador, email.upper(), "MENTOR").status_code == 409


def test_cadastro_de_usuario_com_senha_fraca(client, usuario_no_banco, novo_email):
    organizador = usuario_no_banco(papel="ORGANIZADOR")

    resposta = cadastrar_usuario(client, organizador, novo_email(), "MENTOR", senha="fraca")

    assert resposta.status_code == 422


# --- Hierarquia de cadastro (RN24) ---

PODE_CADASTRAR = {
    "ORGANIZADOR": {p for p in PAPEIS if p != "DEV"},
    "COMITE_CIENTIFICO": {"COMITE_TECNICO", "MENTOR"},
    "MENTOR": set(),
    "COMITE_TECNICO": set(),
    "PARTICIPANTE": set(),
    "DEV": set(PAPEIS),
}


@pytest.mark.parametrize("quem", PAPEIS)
@pytest.mark.parametrize("perfil", PAPEIS)
def test_hierarquia_de_cadastro(quem, perfil):
    assert pode_cadastrar(PapelUsuario(quem), PapelUsuario(perfil)) == (
        perfil in PODE_CADASTRAR[quem]
    )


# --- Perfis que o usuário pode cadastrar (GET /admin/usuarios/perfis) ---


@pytest.mark.parametrize("quem", ["ORGANIZADOR", "COMITE_CIENTIFICO", "DEV"])
def test_lista_os_perfis_que_o_usuario_pode_cadastrar(client, usuario_no_banco, quem):
    usuario = usuario_no_banco(papel=quem)

    resposta = client.get("/admin/usuarios/perfis", headers=com_token(usuario["id"]))

    assert resposta.status_code == 200
    esperado = [papel for papel in PAPEIS if papel in PODE_CADASTRAR[quem]]
    assert resposta.json() == {"perfis": esperado}


@pytest.mark.parametrize("papel", PAPEIS_SEM_ACESSO)
def test_perfil_sem_permissao_nao_lista_perfis(client, usuario_no_banco, papel):
    usuario = usuario_no_banco(papel=papel)

    resposta = client.get("/admin/usuarios/perfis", headers=com_token(usuario["id"]))

    assert resposta.status_code == 403


def test_lista_de_perfis_sem_token(client):
    assert client.get("/admin/usuarios/perfis").status_code == 401


@pytest.mark.parametrize("quem", PAPEIS)
def test_todo_perfil_listado_pode_ser_cadastrado(quem):
    """A lista que a interface mostra e a regra que a API aplica não podem divergir."""
    for perfil in PAPEIS:
        listado = PapelUsuario(perfil) in perfis_cadastraveis(PapelUsuario(quem))
        assert listado == pode_cadastrar(PapelUsuario(quem), PapelUsuario(perfil))
