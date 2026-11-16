"""
Perfil, recuperação de senha, confirmação de e-mail e encerramento de sessão (BE-S5-07).

Estes testes gravam no banco de verdade; as fixtures de conftest.py apagam os dados no final.
Nenhum e-mail é enviado: os links são lidos do corpo gravado na fila (`emails_outbox`).
"""

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest

from app.const.config import settings
from app.security.token import ALGORITMO, criar_token
from tests.conftest import SENHA_PADRAO
from tests.helpers_email import emails_de

SENHA_NOVA = "novasenha456"
MENSAGEM_RECUPERACAO = {
    "detail": "Se existir uma conta ativa com este e-mail, enviamos o link para redefinir a senha."
}
LINK_INVALIDO = {"detail": "Link inválido, expirado ou já utilizado."}


@pytest.fixture(autouse=True)
def _fila_limpa(fila_vazia):
    """Cada teste começa sem e-mails na fila, então só aparece o que ele mesmo gerou."""


@pytest.fixture
def sem_intervalo(monkeypatch):
    """Tira o intervalo mínimo entre pedidos, para o teste pedir links em sequência."""
    monkeypatch.setattr(settings, "SENHA_RESET_INTERVALO_SEGUNDOS", 0)


def cabecalho(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def cabecalho_de(usuario: dict) -> dict:
    return cabecalho(criar_token(usuario["id"]))


def entrar(client, email: str, senha: str = SENHA_PADRAO):
    return client.post("/auth/login", json={"email": email, "senha": senha})


def token_do_email(sql, destinatario: str, tipo: str, *, posicao: int = -1) -> str:
    """O valor puro do link, lido do corpo do e-mail ainda na fila."""
    email = emails_de(sql, destinatario, tipo)[posicao]
    achado = re.search(r"#token=([A-Za-z0-9_-]+)", email["corpo_texto"])
    assert achado, "o e-mail não traz o link com o token"
    return achado.group(1)


def pedir_recuperacao(client, email: str):
    return client.post("/auth/recuperar-senha", json={"email": email})


def redefinir(client, token: str, senha: str = SENHA_NOVA):
    return client.post("/auth/redefinir-senha", json={"token": token, "senha_nova": senha})


def linha_do_usuario(sql, usuario_id) -> dict:
    return sql("SELECT * FROM usuarios WHERE id = :id", id=usuario_id)[0]


def gastar_prazo(sql, usuario_id):
    sql(
        "UPDATE tokens_usuario SET criado_em = (now() AT TIME ZONE 'utc') - interval '2 hours',"
        " expira_em = (now() AT TIME ZONE 'utc') - interval '1 hour' WHERE usuario_id = :u",
        u=usuario_id,
    )


# --- GET e PATCH /me (RF05) ---


def test_me_devolve_os_dados_e_o_alias_antigo(client, usuario_no_banco):
    usuario = usuario_no_banco()

    novo = client.get("/me", headers=cabecalho_de(usuario))
    antigo = client.get("/auth/me", headers=cabecalho_de(usuario))

    assert novo.status_code == 200
    assert novo.json() == antigo.json()
    assert novo.json()["email"] == usuario["email"]
    assert novo.json()["email_confirmado_em"] is None


def test_me_sem_token_ou_com_conta_desativada(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    sql("UPDATE usuarios SET ativo = false WHERE id = :id", id=usuario["id"])

    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=cabecalho_de(usuario)).status_code == 401
    assert client.patch("/me", json={"nome": "X"}, headers=cabecalho_de(usuario)).status_code == 401


def test_patch_me_altera_so_o_que_foi_enviado(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    sql("UPDATE usuarios SET nome = 'Antigo', curso = 'Física' WHERE id = :id", id=usuario["id"])

    resposta = client.patch(
        "/me", json={"nome": "  Nome Novo ", "periodo": 7}, headers=cabecalho_de(usuario)
    )

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Nome Novo"
    linha = linha_do_usuario(sql, usuario["id"])
    assert linha["periodo"] == 7
    assert linha["curso"] == "Física"
    assert linha["atualizado_em"] is not None


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("papel", "ORGANIZADOR"),
        ("ativo", False),
        ("situacao_conta", "ATIVA"),
        ("email", "outro@testes.com"),
        ("max_equipes", 50),
        ("id", "00000000-0000-0000-0000-000000000000"),
        ("versao_sessao", 9),
        ("senha_hash", "x"),
    ],
)
def test_patch_me_recusa_campos_que_a_pessoa_nao_controla(
    client, sql, usuario_no_banco, campo, valor
):
    usuario = usuario_no_banco(papel="COMITE_TECNICO", situacao_conta="PENDENTE")
    antes = linha_do_usuario(sql, usuario["id"])

    resposta = client.patch("/me", json={campo: valor}, headers=cabecalho_de(usuario))

    assert resposta.status_code == 422
    assert linha_do_usuario(sql, usuario["id"]) == antes


def test_patch_me_recusa_nulo_e_nome_vazio(client, usuario_no_banco):
    usuario = usuario_no_banco()

    assert (
        client.patch("/me", json={"nome": None}, headers=cabecalho_de(usuario)).status_code == 422
    )
    assert client.patch("/me", json={"nome": ""}, headers=cabecalho_de(usuario)).status_code == 422
    assert (
        client.patch("/me", json={"periodo": 0}, headers=cabecalho_de(usuario)).status_code == 422
    )


def test_dados_de_mentor_so_para_mentor(client, sql, usuario_no_banco):
    participante = usuario_no_banco()
    mentor = usuario_no_banco(papel="MENTOR")

    recusado = client.patch(
        "/me", json={"empresa_parceira": "ACME"}, headers=cabecalho_de(participante)
    )
    aceito = client.patch(
        "/me",
        json={"empresa_parceira": "ACME", "area_atuacao": "Dados"},
        headers=cabecalho_de(mentor),
    )

    assert recusado.status_code == 422
    assert aceito.status_code == 200
    assert aceito.json()["empresa_parceira"] == "ACME"


def test_conta_pendente_consulta_e_edita_o_proprio_perfil(client, usuario_no_banco):
    usuario = usuario_no_banco(situacao_conta="PENDENTE")

    assert client.get("/me", headers=cabecalho_de(usuario)).status_code == 200
    resposta = client.patch("/me", json={"curso": "Letras"}, headers=cabecalho_de(usuario))
    assert resposta.status_code == 200
    assert resposta.json()["situacao_conta"] == "PENDENTE"


# --- Recuperação de senha (RF04) ---


def test_pedido_responde_igual_com_ou_sem_conta(client, sql, usuario_no_banco, novo_email):
    usuario = usuario_no_banco()
    inexistente = novo_email()

    com_conta = pedir_recuperacao(client, usuario["email"])
    sem_conta = pedir_recuperacao(client, inexistente)

    assert com_conta.status_code == sem_conta.status_code == 202
    assert com_conta.json() == sem_conta.json() == MENSAGEM_RECUPERACAO
    assert len(emails_de(sql, usuario["email"], "RECUPERACAO_SENHA")) == 1
    assert emails_de(sql, inexistente) == []


def test_pedido_ignora_maiusculas_no_email(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()

    assert pedir_recuperacao(client, usuario["email"].upper()).status_code == 202

    assert len(emails_de(sql, usuario["email"], "RECUPERACAO_SENHA")) == 1


def test_email_de_recuperacao_traz_so_o_link(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()

    pedir_recuperacao(client, usuario["email"])

    [email] = emails_de(sql, usuario["email"], "RECUPERACAO_SENHA")
    assert "/redefinir-senha#token=" in email["corpo_texto"]
    assert str(settings.SENHA_RESET_MINUTOS) in email["corpo_texto"]
    assert SENHA_PADRAO not in email["corpo_texto"]


def test_token_guardado_so_como_hash(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])

    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    [linha] = sql("SELECT * FROM tokens_usuario WHERE usuario_id = :u", u=usuario["id"])
    assert linha["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(dict(linha))
    assert linha["finalidade"] == "REDEFINICAO_SENHA"
    assert linha["utilizado_em"] is None


@pytest.mark.parametrize(
    "preparar",
    [
        pytest.param(
            lambda sql, u: sql("UPDATE usuarios SET ativo = false WHERE id = :i", i=u),
            id="desativada",
        ),
        pytest.param(
            lambda sql, u: sql("UPDATE usuarios SET senha_hash = NULL WHERE id = :i", i=u),
            id="sem-senha",
        ),
    ],
)
def test_sem_email_para_conta_que_nao_pode_entrar(client, sql, usuario_no_banco, preparar):
    usuario = usuario_no_banco()
    preparar(sql, usuario["id"])

    resposta = pedir_recuperacao(client, usuario["email"])

    assert resposta.status_code == 202
    assert resposta.json() == MENSAGEM_RECUPERACAO
    assert emails_de(sql, usuario["email"]) == []


def test_conta_pendente_pode_recuperar_a_senha(client, sql, usuario_no_banco):
    usuario = usuario_no_banco(situacao_conta="PENDENTE")

    pedir_recuperacao(client, usuario["email"])

    assert len(emails_de(sql, usuario["email"], "RECUPERACAO_SENHA")) == 1


def test_pedidos_em_sequencia_nao_geram_outro_email(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()

    primeiro = pedir_recuperacao(client, usuario["email"])
    segundo = pedir_recuperacao(client, usuario["email"])

    assert primeiro.json() == segundo.json()
    assert len(emails_de(sql, usuario["email"], "RECUPERACAO_SENHA")) == 1


def test_novo_pedido_gasta_o_link_anterior(client, sql, usuario_no_banco, sem_intervalo):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])
    primeiro = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")
    pedir_recuperacao(client, usuario["email"])
    segundo = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    assert primeiro != segundo
    assert redefinir(client, primeiro).status_code == 400
    assert redefinir(client, segundo).status_code == 204


def test_redefinir_troca_a_senha_e_encerra_as_sessoes(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    sessao_antiga = entrar(client, usuario["email"]).json()["access_token"]
    assert client.get("/me", headers=cabecalho(sessao_antiga)).status_code == 200
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    resposta = redefinir(client, token)

    assert resposta.status_code == 204
    assert resposta.content == b""
    assert client.get("/me", headers=cabecalho(sessao_antiga)).status_code == 401
    assert entrar(client, usuario["email"]).status_code == 401
    novo_login = entrar(client, usuario["email"], SENHA_NOVA)
    assert novo_login.status_code == 200
    assert (
        client.get("/me", headers=cabecalho(novo_login.json()["access_token"])).status_code == 200
    )


def test_redefinir_libera_conta_bloqueada_e_confirma_o_email(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    for _ in range(settings.LOGIN_MAX_TENTATIVAS):
        entrar(client, usuario["email"], "errada1234")
    assert entrar(client, usuario["email"]).status_code == 429
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    assert redefinir(client, token).status_code == 204

    linha = linha_do_usuario(sql, usuario["id"])
    assert linha["bloqueado_ate"] is None
    assert linha["tentativas_login"] == 0
    assert linha["email_confirmado_em"] is not None
    assert entrar(client, usuario["email"], SENHA_NOVA).status_code == 200


def test_link_so_funciona_uma_vez(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    assert redefinir(client, token).status_code == 204
    repetido = redefinir(client, token, "outrasenha789")

    assert repetido.status_code == 400
    assert repetido.json() == LINK_INVALIDO
    assert entrar(client, usuario["email"], SENHA_NOVA).status_code == 200
    assert entrar(client, usuario["email"], "outrasenha789").status_code == 401


def test_link_vencido_e_recusado(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")
    gastar_prazo(sql, usuario["id"])

    resposta = redefinir(client, token)

    assert resposta.status_code == 400
    assert resposta.json() == LINK_INVALIDO
    assert entrar(client, usuario["email"]).status_code == 200


def test_token_inventado_tem_a_mesma_resposta_do_vencido(client):
    resposta = redefinir(client, "a" * 43)

    assert resposta.status_code == 400
    assert resposta.json() == LINK_INVALIDO


@pytest.mark.parametrize("token", ["curto", "x" * 200])
def test_token_com_tamanho_invalido(client, token):
    assert redefinir(client, token).status_code == 422


def test_senha_fraca_nao_gasta_o_link(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    assert redefinir(client, token, "curta").status_code == 422
    assert redefinir(client, token, "somenteletras").status_code == 422

    assert redefinir(client, token).status_code == 204


def test_link_de_conta_desativada_depois_do_pedido_e_recusado(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")
    sql("UPDATE usuarios SET ativo = false WHERE id = :id", id=usuario["id"])

    assert redefinir(client, token).status_code == 400

    [linha] = sql("SELECT utilizado_em FROM tokens_usuario WHERE usuario_id = :u", u=usuario["id"])
    assert linha["utilizado_em"] is None  # o uso foi desfeito junto com a recusa
    assert entrar(client, usuario["email"], SENHA_NOVA).status_code == 401


def test_dois_usos_simultaneos_do_mesmo_link(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [
            pool.submit(redefinir, client, token, "primeira123"),
            pool.submit(redefinir, client, token, "segunda456"),
        ]
        codigos = sorted(f.result().status_code for f in futuros)

    assert codigos == [204, 400]
    aceitas = [
        senha
        for senha in ("primeira123", "segunda456")
        if entrar(client, usuario["email"], senha).status_code == 200
    ]
    assert len(aceitas) == 1


# --- Troca de senha logado (RF05, RNF15) ---


def test_trocar_senha_devolve_novo_token_e_derruba_os_antigos(client, usuario_no_banco):
    usuario = usuario_no_banco()
    sessao_a = entrar(client, usuario["email"]).json()["access_token"]
    sessao_b = entrar(client, usuario["email"]).json()["access_token"]

    resposta = client.post(
        "/me/senha",
        json={"senha_atual": SENHA_PADRAO, "senha_nova": SENHA_NOVA},
        headers=cabecalho(sessao_a),
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["usuario"]["email"] == usuario["email"]
    assert client.get("/me", headers=cabecalho(sessao_a)).status_code == 401
    assert client.get("/me", headers=cabecalho(sessao_b)).status_code == 401
    assert client.get("/me", headers=cabecalho(corpo["access_token"])).status_code == 200
    assert entrar(client, usuario["email"]).status_code == 401
    assert entrar(client, usuario["email"], SENHA_NOVA).status_code == 200


def test_trocar_senha_com_senha_atual_errada(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    antes = linha_do_usuario(sql, usuario["id"])["senha_hash"]

    resposta = client.post(
        "/me/senha",
        json={"senha_atual": "errada1234", "senha_nova": SENHA_NOVA},
        headers=cabecalho_de(usuario),
    )

    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "Senha atual incorreta."}
    linha = linha_do_usuario(sql, usuario["id"])
    assert linha["senha_hash"] == antes
    assert linha["tentativas_login"] == 1
    # a sessão segue válida: é um erro de confirmação, não de autenticação
    assert client.get("/me", headers=cabecalho_de(usuario)).status_code == 200


def test_senha_atual_errada_repetida_bloqueia_a_conta(client, usuario_no_banco):
    usuario = usuario_no_banco()
    dados = {"senha_atual": "errada1234", "senha_nova": SENHA_NOVA}

    for _ in range(settings.LOGIN_MAX_TENTATIVAS):
        assert (
            client.post("/me/senha", json=dados, headers=cabecalho_de(usuario)).status_code == 403
        )
    certa = client.post(
        "/me/senha",
        json={"senha_atual": SENHA_PADRAO, "senha_nova": SENHA_NOVA},
        headers=cabecalho_de(usuario),
    )

    assert certa.status_code == 429
    assert "Retry-After" in certa.headers
    assert entrar(client, usuario["email"]).status_code == 429


@pytest.mark.parametrize(
    "senha_nova",
    [SENHA_PADRAO, "curta1", "somenteletras", "12345678901"],
    ids=["igual", "curta", "sem-numero", "sem-letra"],
)
def test_trocar_senha_recusa_senha_nova_ruim(client, usuario_no_banco, senha_nova):
    usuario = usuario_no_banco()

    resposta = client.post(
        "/me/senha",
        json={"senha_atual": SENHA_PADRAO, "senha_nova": senha_nova},
        headers=cabecalho_de(usuario),
    )

    assert resposta.status_code == 422
    assert entrar(client, usuario["email"]).status_code == 200


def test_trocar_senha_gasta_pedido_de_redefinicao_aberto(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    troca = client.post(
        "/me/senha",
        json={"senha_atual": SENHA_PADRAO, "senha_nova": SENHA_NOVA},
        headers=cabecalho_de(usuario),
    )

    assert troca.status_code == 200
    assert redefinir(client, token, "outrasenha789").status_code == 400
    assert entrar(client, usuario["email"], SENHA_NOVA).status_code == 200


# --- Encerramento e aviso de expiração da sessão (RF09) ---


def test_logout_invalida_todos_os_tokens_da_conta(client, usuario_no_banco):
    usuario = usuario_no_banco()
    sessao_a = entrar(client, usuario["email"]).json()["access_token"]
    sessao_b = entrar(client, usuario["email"]).json()["access_token"]

    resposta = client.post("/auth/logout", headers=cabecalho(sessao_a))

    assert resposta.status_code == 204
    assert client.get("/me", headers=cabecalho(sessao_a)).status_code == 401
    assert client.get("/me", headers=cabecalho(sessao_b)).status_code == 401
    novo = entrar(client, usuario["email"])
    assert client.get("/me", headers=cabecalho(novo.json()["access_token"])).status_code == 200


def test_logout_sem_token_e_com_token_ja_encerrado(client, usuario_no_banco):
    usuario = usuario_no_banco()
    sessao = entrar(client, usuario["email"]).json()["access_token"]

    assert client.post("/auth/logout").status_code == 401
    assert client.post("/auth/logout", headers=cabecalho(sessao)).status_code == 204
    assert client.post("/auth/logout", headers=cabecalho(sessao)).status_code == 401


def test_conta_pendente_pode_encerrar_a_sessao(client, usuario_no_banco):
    usuario = usuario_no_banco(situacao_conta="PENDENTE")

    assert client.post("/auth/logout", headers=cabecalho_de(usuario)).status_code == 204


def test_sessao_informa_quando_vence(client, usuario_no_banco):
    usuario = usuario_no_banco()
    sessao = entrar(client, usuario["email"]).json()["access_token"]

    resposta = client.get("/auth/sessao", headers=cabecalho(sessao))

    assert resposta.status_code == 200
    corpo = resposta.json()
    limite = settings.JWT_EXPIRE_MINUTES * 60
    assert limite - 30 <= corpo["segundos_restantes"] <= limite
    assert corpo["expira_em"]
    assert client.get("/auth/sessao").status_code == 401


def test_token_com_versao_de_sessao_diferente_e_recusado(client, usuario_no_banco):
    usuario = usuario_no_banco()

    assert client.get("/me", headers=cabecalho(criar_token(usuario["id"], 0))).status_code == 200
    assert client.get("/me", headers=cabecalho(criar_token(usuario["id"], 1))).status_code == 401


def test_token_antigo_sem_versao_vale_como_zero(client, usuario_no_banco):
    from datetime import UTC, datetime, timedelta

    usuario = usuario_no_banco()
    agora = datetime.now(UTC)
    antigo = jwt.encode(
        {"sub": str(usuario["id"]), "iat": agora, "exp": agora + timedelta(minutes=5)},
        settings.JWT_SECRET,
        algorithm=ALGORITMO,
    )

    assert client.get("/me", headers=cabecalho(antigo)).status_code == 200


def test_versao_de_sessao_invalida_no_token(client, usuario_no_banco):
    from datetime import UTC, datetime, timedelta

    usuario = usuario_no_banco()
    agora = datetime.now(UTC)
    for versao in ("0", None, 1.5, True):
        token = jwt.encode(
            {
                "sub": str(usuario["id"]),
                "sv": versao,
                "exp": agora + timedelta(minutes=5),
            },
            settings.JWT_SECRET,
            algorithm=ALGORITMO,
        )
        assert client.get("/me", headers=cabecalho(token)).status_code == 401


# --- Confirmação de e-mail (RF01) ---


def cadastrar_participante(client, email: str):
    return client.post(
        "/auth/cadastro",
        json={
            "nome": "Maria Souza",
            "email": email,
            "senha": SENHA_PADRAO,
            "instituicao": "UFPA",
            "curso": "Sistemas de Informação",
            "periodo": 4,
            "comprovante_url": "https://res.cloudinary.com/demo/comprovante.pdf",
        },
    )


def test_cadastro_envia_o_link_de_confirmacao(client, sql, hackathon_aberto, novo_email):
    email = novo_email()

    assert cadastrar_participante(client, email).status_code == 201

    [enviado] = emails_de(sql, email, "CONFIRMACAO_EMAIL")
    assert "/confirmar-email#token=" in enviado["corpo_texto"]
    assert linha_do_usuario_por_email(sql, email)["email_confirmado_em"] is None


def linha_do_usuario_por_email(sql, email: str) -> dict:
    return sql("SELECT * FROM usuarios WHERE lower(email) = lower(:e)", e=email)[0]


def test_confirmar_email_marca_o_endereco_e_nao_exige_login(
    client, sql, hackathon_aberto, novo_email
):
    email = novo_email()
    cadastrar_participante(client, email)
    token = token_do_email(sql, email, "CONFIRMACAO_EMAIL")

    resposta = client.post("/auth/confirmar-email", json={"token": token})

    assert resposta.status_code == 200
    assert resposta.json()["email"] == email
    assert resposta.json()["email_confirmado_em"] is not None
    assert linha_do_usuario_por_email(sql, email)["email_confirmado_em"] is not None
    repetido = client.post("/auth/confirmar-email", json={"token": token})
    assert repetido.status_code == 400
    assert repetido.json() == LINK_INVALIDO


def test_confirmacao_nao_bloqueia_o_login(client, hackathon_aberto, novo_email):
    email = novo_email()
    cadastrar_participante(client, email)

    assert entrar(client, email).status_code == 200


def test_confirmar_com_token_de_outra_finalidade(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    pedir_recuperacao(client, usuario["email"])
    token = token_do_email(sql, usuario["email"], "RECUPERACAO_SENHA")

    assert client.post("/auth/confirmar-email", json={"token": token}).status_code == 400
    # e o contrário: link de confirmação não redefine senha
    client.post("/me/confirmacao-email", headers=cabecalho_de(usuario))
    confirmacao = token_do_email(sql, usuario["email"], "CONFIRMACAO_EMAIL")
    assert redefinir(client, confirmacao).status_code == 400


def test_reenviar_confirmacao(client, sql, usuario_no_banco, sem_intervalo):
    usuario = usuario_no_banco()

    primeiro = client.post("/me/confirmacao-email", headers=cabecalho_de(usuario))
    segundo = client.post("/me/confirmacao-email", headers=cabecalho_de(usuario))

    assert primeiro.status_code == segundo.status_code == 202
    emails = emails_de(sql, usuario["email"], "CONFIRMACAO_EMAIL")
    assert len(emails) == 2
    antigo = token_do_email(sql, usuario["email"], "CONFIRMACAO_EMAIL", posicao=0)
    novo = token_do_email(sql, usuario["email"], "CONFIRMACAO_EMAIL", posicao=1)
    assert client.post("/auth/confirmar-email", json={"token": antigo}).status_code == 400
    assert client.post("/auth/confirmar-email", json={"token": novo}).status_code == 200


def test_reenviar_confirmacao_em_sequencia_nao_duplica(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()

    client.post("/me/confirmacao-email", headers=cabecalho_de(usuario))
    segundo = client.post("/me/confirmacao-email", headers=cabecalho_de(usuario))

    assert segundo.status_code == 202
    assert len(emails_de(sql, usuario["email"], "CONFIRMACAO_EMAIL")) == 1


def test_reenviar_confirmacao_de_email_ja_confirmado(client, sql, usuario_no_banco):
    usuario = usuario_no_banco()
    sql("UPDATE usuarios SET email_confirmado_em = now() WHERE id = :id", id=usuario["id"])

    resposta = client.post("/me/confirmacao-email", headers=cabecalho_de(usuario))

    assert resposta.status_code == 409
    assert emails_de(sql, usuario["email"]) == []


# --- Troca de e-mail com confirmação (RF01, RF05) ---


def pedir_troca(client, usuario: dict, novo: str, senha: str = SENHA_PADRAO):
    return client.post(
        "/me/email", json={"novo_email": novo, "senha": senha}, headers=cabecalho_de(usuario)
    )


def test_troca_de_email_so_vale_depois_de_confirmar(client, sql, usuario_no_banco, novo_email):
    usuario = usuario_no_banco()
    novo = novo_email()

    pedido = pedir_troca(client, usuario, novo.upper())

    assert pedido.status_code == 202
    assert linha_do_usuario(sql, usuario["id"])["email"] == usuario["email"]
    assert emails_de(sql, usuario["email"]) == []  # o aviso vai só ao endereço novo
    token = token_do_email(sql, novo, "CONFIRMACAO_EMAIL")

    confirmado = client.post("/auth/confirmar-email", json={"token": token})

    assert confirmado.status_code == 200
    assert confirmado.json()["email"] == novo.lower()
    linha = linha_do_usuario(sql, usuario["id"])
    assert linha["email"] == novo.lower()
    assert linha["email_confirmado_em"] is not None
    assert entrar(client, usuario["email"]).status_code == 401
    assert entrar(client, novo).status_code == 200


def test_troca_de_email_exige_a_senha(client, sql, usuario_no_banco, novo_email):
    usuario = usuario_no_banco()

    resposta = pedir_troca(client, usuario, novo_email(), senha="errada1234")

    assert resposta.status_code == 403
    assert sql("SELECT 1 FROM tokens_usuario WHERE usuario_id = :u", u=usuario["id"]) == []


def test_troca_para_email_de_outra_conta(client, usuario_no_banco):
    usuario = usuario_no_banco()
    outro = usuario_no_banco()

    assert pedir_troca(client, usuario, outro["email"].upper()).status_code == 409


def test_troca_para_o_mesmo_email(client, usuario_no_banco):
    usuario = usuario_no_banco()

    assert pedir_troca(client, usuario, usuario["email"].upper()).status_code == 422


def test_troca_com_email_invalido(client, usuario_no_banco):
    usuario = usuario_no_banco()

    assert pedir_troca(client, usuario, "isto-nao-e-email").status_code == 422


def test_outro_pedido_de_troca_gasta_o_anterior(
    client, sql, usuario_no_banco, novo_email, sem_intervalo
):
    usuario = usuario_no_banco()
    primeiro, segundo = novo_email(), novo_email()
    pedir_troca(client, usuario, primeiro)
    pedir_troca(client, usuario, segundo)

    token_antigo = token_do_email(sql, primeiro, "CONFIRMACAO_EMAIL")
    token_novo = token_do_email(sql, segundo, "CONFIRMACAO_EMAIL")

    assert client.post("/auth/confirmar-email", json={"token": token_antigo}).status_code == 400
    assert client.post("/auth/confirmar-email", json={"token": token_novo}).status_code == 200
    assert linha_do_usuario(sql, usuario["id"])["email"] == segundo.lower()


def test_endereco_tomado_antes_da_confirmacao(client, sql, usuario_no_banco, novo_email):
    usuario = usuario_no_banco()
    novo = novo_email()
    pedir_troca(client, usuario, novo)
    token = token_do_email(sql, novo, "CONFIRMACAO_EMAIL")
    # outra conta fica com o endereço no meio do caminho
    sql(
        "INSERT INTO usuarios (email, papel, ativo) VALUES (:e, 'PARTICIPANTE', true)",
        e=novo,
    )

    resposta = client.post("/auth/confirmar-email", json={"token": token})

    assert resposta.status_code == 409
    assert linha_do_usuario(sql, usuario["id"])["email"] == usuario["email"]


def test_confirmacao_de_conta_desativada_e_recusada(client, sql, usuario_no_banco, novo_email):
    usuario = usuario_no_banco()
    novo = novo_email()
    pedir_troca(client, usuario, novo)
    token = token_do_email(sql, novo, "CONFIRMACAO_EMAIL")
    sql("UPDATE usuarios SET ativo = false WHERE id = :id", id=usuario["id"])

    assert client.post("/auth/confirmar-email", json={"token": token}).status_code == 400
    assert linha_do_usuario(sql, usuario["id"])["email"] == usuario["email"]
