"""
Cadastro de participante (RF01) e login (RF02).

Estes testes gravam no banco de verdade; as fixtures de conftest.py apagam os dados no final.
"""

import pytest

from app.const.config import settings
from app.security.token import ler_token

SENHA = "segredo123"
SENHA_ERRADA = "senha-errada1"
LINK_COMPROVANTE = "https://res.cloudinary.com/demo/comprovante.pdf"
MENSAGEM_LOGIN_INVALIDO = {"detail": "E-mail ou senha inválidos."}


def dados_de_cadastro(email: str, **mudancas) -> dict:
    dados = {
        "nome": "João da Silva",
        "email": email,
        "senha": SENHA,
        "instituicao": "UFPA",
        "curso": "Sistemas de Informação",
        "periodo": 5,
        "comprovante_url": LINK_COMPROVANTE,
    }
    return {**dados, **mudancas}


def cadastrar(client, email: str, **mudancas):
    return client.post("/auth/cadastro", json=dados_de_cadastro(email, **mudancas))


def fazer_login(client, email: str, senha: str = SENHA):
    return client.post("/auth/login", json={"email": email, "senha": senha})


def estado_de_login(sql, email: str):
    return sql(
        "SELECT tentativas_login, bloqueado_ate FROM usuarios WHERE lower(email) = lower(:e)",
        e=email,
    )[0]


# --- Cadastro ---


def test_cadastro_cria_participante_com_conta_pendente(client, sql, hackathon_aberto, novo_email):
    email = novo_email()

    resposta = cadastrar(client, email)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["email"] == email
    assert corpo["papel"] == "PARTICIPANTE"
    assert corpo["situacao_conta"] == "PENDENTE"
    assert corpo["ativo"] is True
    assert "senha" not in corpo
    assert "senha_hash" not in corpo

    usuario = sql("SELECT senha_hash FROM usuarios WHERE email = :e", e=email)[0]
    assert usuario["senha_hash"].startswith("$argon2")
    assert SENHA not in usuario["senha_hash"]


def test_cadastro_registra_comprovante_pendente_no_hackathon_aberto(
    client, sql, hackathon_aberto, novo_email
):
    id_ = cadastrar(client, novo_email()).json()["id"]

    comprovante = sql(
        "SELECT hackathon_id, arquivo_url, status::text AS status"
        " FROM comprovantes_vinculo WHERE usuario_id = :u",
        u=id_,
    )
    assert len(comprovante) == 1
    assert comprovante[0]["hackathon_id"] == hackathon_aberto
    assert comprovante[0]["arquivo_url"] == LINK_COMPROVANTE
    assert comprovante[0]["status"] == "PENDENTE"


def test_cadastro_ignora_edicoes_mais_recentes_fora_do_periodo(
    client, sql, hackathon_aberto, novo_email, edicoes_fora_do_periodo
):
    resposta = cadastrar(client, novo_email())

    assert resposta.status_code == 201, resposta.text
    comprovante = sql(
        "SELECT hackathon_id FROM comprovantes_vinculo WHERE usuario_id = :u",
        u=resposta.json()["id"],
    )
    assert [c["hackathon_id"] for c in comprovante] == [hackathon_aberto]
    assert hackathon_aberto not in edicoes_fora_do_periodo


def test_cadastro_guarda_email_em_minusculas(client, hackathon_aberto, novo_email):
    email = novo_email()

    resposta = cadastrar(client, email.upper())

    assert resposta.status_code == 201
    assert resposta.json()["email"] == email.lower()


def test_cadastro_ignora_o_perfil_enviado_pelo_cliente(client, hackathon_aberto, novo_email):
    resposta = cadastrar(client, novo_email(), papel="ORGANIZADOR")

    assert resposta.status_code == 201
    assert resposta.json()["papel"] == "PARTICIPANTE"


def test_cadastro_com_email_repetido(client, hackathon_aberto, novo_email):
    email = novo_email()
    cadastrar(client, email)

    assert cadastrar(client, email).status_code == 409


def test_cadastro_com_email_repetido_em_outras_maiusculas(client, hackathon_aberto, novo_email):
    email = novo_email()
    cadastrar(client, email)

    assert cadastrar(client, email.upper()).status_code == 409


@pytest.mark.parametrize("senha", ["abc123", "somenteletras", "12345678", "a" * 129 + "1"])
def test_cadastro_com_senha_fraca(client, hackathon_aberto, novo_email, senha):
    assert cadastrar(client, novo_email(), senha=senha).status_code == 422


@pytest.mark.parametrize(
    "campo", ["nome", "email", "senha", "instituicao", "curso", "periodo", "comprovante_url"]
)
def test_cadastro_sem_campo_obrigatorio(client, hackathon_aberto, novo_email, campo):
    dados = dados_de_cadastro(novo_email())
    del dados[campo]

    assert client.post("/auth/cadastro", json=dados).status_code == 422


@pytest.mark.parametrize(
    "link",
    [
        "http://res.cloudinary.com/demo/comprovante.pdf",
        "https://res.cloudinary.com/demo/comprovante.exe",
        "https://res.cloudinary.com/demo/comprovante",
        "comprovante.pdf",
    ],
)
def test_cadastro_com_comprovante_invalido(client, hackathon_aberto, novo_email, link):
    assert cadastrar(client, novo_email(), comprovante_url=link).status_code == 422


@pytest.mark.parametrize("extensao", ["pdf", "PNG", "jpg", "jpeg"])
def test_cadastro_aceita_pdf_e_imagens(client, hackathon_aberto, novo_email, extensao):
    link = f"https://res.cloudinary.com/demo/comprovante.{extensao}"

    assert cadastrar(client, novo_email(), comprovante_url=link).status_code == 201


def test_cadastro_sem_hackathon_com_inscricoes(client, sql, novo_email, monkeypatch):
    async def nenhum(db):
        return None

    monkeypatch.setattr("app.services.auth.get_hackathon_com_inscricoes", nenhum)
    email = novo_email()

    assert cadastrar(client, email).status_code == 409
    assert sql("SELECT 1 FROM usuarios WHERE email = :e", e=email) == []


# --- Login ---


def test_login_devolve_token_do_usuario(client, usuario_no_banco):
    usuario = usuario_no_banco()

    resposta = fazer_login(client, usuario["email"])

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["token_type"] == "bearer"
    assert corpo["expires_in"] == settings.JWT_EXPIRE_MINUTES * 60
    assert ler_token(corpo["access_token"]) == usuario["id"]


def test_login_sem_diferenciar_maiusculas_no_email(client, usuario_no_banco):
    usuario = usuario_no_banco()

    assert fazer_login(client, usuario["email"].upper()).status_code == 200


def test_conta_pendente_consegue_entrar(client, usuario_no_banco):
    usuario = usuario_no_banco(situacao_conta="PENDENTE")

    assert fazer_login(client, usuario["email"]).status_code == 200


def test_senha_errada_e_email_inexistente_dao_a_mesma_resposta(client, usuario_no_banco):
    usuario = usuario_no_banco()

    senha_errada = fazer_login(client, usuario["email"], SENHA_ERRADA)
    sem_conta = fazer_login(client, "ninguem@testes.com")

    assert senha_errada.status_code == sem_conta.status_code == 401
    assert senha_errada.json() == sem_conta.json() == MENSAGEM_LOGIN_INVALIDO


def test_login_de_conta_desativada(client, usuario_no_banco):
    usuario = usuario_no_banco(ativo=False)

    resposta = fazer_login(client, usuario["email"])

    assert resposta.status_code == 401
    assert resposta.json() == MENSAGEM_LOGIN_INVALIDO


def test_login_de_conta_sem_senha(client, usuario_no_banco):
    usuario = usuario_no_banco(senha=None)

    resposta = fazer_login(client, usuario["email"], SENHA)

    assert resposta.status_code == 401
    assert resposta.json() == MENSAGEM_LOGIN_INVALIDO


def test_login_com_email_invalido(client):
    assert client.post("/auth/login", json={"email": "x", "senha": SENHA}).status_code == 422


# --- Bloqueio por tentativas (RF02) ---


def test_conta_bloqueia_depois_de_varias_falhas_seguidas(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()

    for _ in range(settings.LOGIN_MAX_TENTATIVAS):
        assert fazer_login(client, usuario["email"], SENHA_ERRADA).status_code == 401

    # Bloqueada: nem a senha correta entra
    resposta = fazer_login(client, usuario["email"])
    assert resposta.status_code == 429
    assert 0 < int(resposta.headers["Retry-After"]) <= settings.LOGIN_BLOQUEIO_MINUTOS * 60
    assert estado_de_login(sql, usuario["email"])["bloqueado_ate"] is not None


def test_bloqueio_acaba_com_o_tempo(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    for _ in range(settings.LOGIN_MAX_TENTATIVAS):
        fazer_login(client, usuario["email"], SENHA_ERRADA)
    sql(
        "UPDATE usuarios SET bloqueado_ate = (now() AT TIME ZONE 'utc') - interval '1 minute'"
        " WHERE email = :e",
        e=usuario["email"],
    )

    assert fazer_login(client, usuario["email"]).status_code == 200

    estado = estado_de_login(sql, usuario["email"])
    assert estado["tentativas_login"] == 0
    assert estado["bloqueado_ate"] is None


def test_login_correto_zera_as_falhas(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    falhas = settings.LOGIN_MAX_TENTATIVAS - 1
    for _ in range(falhas):
        fazer_login(client, usuario["email"], SENHA_ERRADA)
    assert estado_de_login(sql, usuario["email"])["tentativas_login"] == falhas

    assert fazer_login(client, usuario["email"]).status_code == 200

    assert estado_de_login(sql, usuario["email"])["tentativas_login"] == 0


# --- Dados do usuário no login (a interface escolhe o painel pelo papel) ---


def test_login_devolve_os_dados_do_usuario(client, usuario_no_banco):
    usuario = usuario_no_banco(papel="MENTOR", situacao_conta="PENDENTE")

    corpo = fazer_login(client, usuario["email"]).json()

    assert corpo["usuario"]["email"] == usuario["email"]
    assert corpo["usuario"]["papel"] == "MENTOR"
    assert corpo["usuario"]["situacao_conta"] == "PENDENTE"
    assert "senha_hash" not in corpo["usuario"]
