"""BE-S5-05: provedores de e-mail e configuração por ambiente (RNF28). Não usam o banco."""

import asyncio
import logging
import smtplib

import pytest
from pydantic import SecretStr, ValidationError

from app.const.config import Settings
from app.integrations import email as integracao
from app.integrations.email import (
    ErroEnvioPermanente,
    ErroEnvioTemporario,
    MensagemEmail,
    ProvedorConsole,
    ProvedorMemoria,
    ProvedorSmtp,
)

SENHA_SMTP = "senha-super-secreta-do-smtp"

MENSAGEM = MensagemEmail(
    destinatario="maria@example.com",
    destinatario_nome="Maria Souza",
    assunto="Convite para participar",
    texto="Corpo em texto",
    html="<p>Corpo em HTML</p>",
)


def provedor(seguranca: str = "starttls", usuario: str = "apikey") -> ProvedorSmtp:
    return ProvedorSmtp(
        host="smtp.example.com",
        porta=587,
        usuario=usuario,
        senha=SENHA_SMTP,
        seguranca=seguranca,
        timeout=5,
        remetente_nome="Hackathon UFPA",
        remetente_endereco="nao-responder@hackathon.example",
    )


class SmtpFalso:
    """Substitui smtplib.SMTP e SMTP_SSL: registra as chamadas, ou levanta o erro programado."""

    chamadas: list = []
    erro: Exception | None = None

    def __init__(self, host, porta, timeout=None, context=None):
        self.registrar("conectar", host, porta, timeout, type(self).__name__)

    @classmethod
    def registrar(cls, *evento):
        SmtpFalso.chamadas.append(evento)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.registrar("sair")

    def starttls(self, context=None):
        self.registrar("starttls")

    def login(self, usuario, senha):
        self.registrar("login", usuario, senha)

    def send_message(self, mensagem):
        self.registrar("enviar", mensagem)
        if SmtpFalso.erro:
            raise SmtpFalso.erro


class SmtpSslFalso(SmtpFalso):
    pass


@pytest.fixture
def smtp(monkeypatch):
    SmtpFalso.chamadas = []
    SmtpFalso.erro = None
    monkeypatch.setattr(smtplib, "SMTP", SmtpFalso)
    monkeypatch.setattr(smtplib, "SMTP_SSL", SmtpSslFalso)
    return SmtpFalso


def enviar(p: ProvedorSmtp, mensagem: MensagemEmail = MENSAGEM):
    return asyncio.run(p.enviar(mensagem))


# --- Montagem da mensagem ---


def test_mensagem_tem_remetente_unico_texto_e_alternativa_html():
    email = provedor().montar(MENSAGEM)

    assert email["From"] == "Hackathon UFPA <nao-responder@hackathon.example>"
    assert email["To"] == "Maria Souza <maria@example.com>"
    assert email["Subject"] == "Convite para participar"
    assert email["Auto-Submitted"] == "auto-generated"
    assert email["Message-ID"].endswith("@hackathon.example>")
    assert email.get_content_type() == "multipart/alternative"
    texto, html = email.get_payload()
    assert texto.get_content_type() == "text/plain"
    assert texto.get_content().strip() == "Corpo em texto"
    assert html.get_content_type() == "text/html"
    assert "Corpo em HTML" in html.get_content()


def test_nome_e_assunto_com_acento_sao_aceitos():
    mensagem = MensagemEmail(
        destinatario="jose@example.com",
        destinatario_nome="José Araújo",
        assunto="Inscrição concluída",
        texto="Olá",
        html="<p>Olá</p>",
    )

    email = provedor().montar(mensagem)

    assert email["Subject"] == "Inscrição concluída"
    assert "jose@example.com" in str(email["To"])


@pytest.mark.parametrize(
    "alteracao",
    [
        {"destinatario": "a@example.com\r\nBcc: outro@example.com"},
        {"destinatario_nome": "Maria\nBcc: outro@example.com"},
        {"assunto": "Oi\r\nBcc: outro@example.com"},
    ],
    ids=["destinatario", "nome", "assunto"],
)
def test_quebra_de_linha_em_cabecalho_e_recusada_sem_chegar_ao_servidor(smtp, alteracao):
    mensagem = MensagemEmail(**{**MENSAGEM.__dict__, **alteracao})

    with pytest.raises(ErroEnvioPermanente, match="Mensagem inválida"):
        enviar(provedor(), mensagem)

    assert smtp.chamadas == []


# --- Conexão e autenticação ---


def test_starttls_autentica_e_envia_uma_vez(smtp):
    mensagem_id = enviar(provedor("starttls"))

    assert [c[0] for c in smtp.chamadas] == ["conectar", "starttls", "login", "enviar", "sair"]
    assert smtp.chamadas[0][1:] == ("smtp.example.com", 587, 5, "SmtpFalso")
    assert smtp.chamadas[2][1:] == ("apikey", SENHA_SMTP)
    assert mensagem_id.startswith("<") and mensagem_id.endswith("@hackathon.example>")


def test_ssl_usa_conexao_segura_desde_o_inicio_sem_starttls(smtp):
    enviar(provedor("ssl"))

    assert [c[0] for c in smtp.chamadas] == ["conectar", "login", "enviar", "sair"]
    assert smtp.chamadas[0][4] == "SmtpSslFalso"


def test_sem_seguranca_e_sem_usuario_so_conecta_e_envia(smtp):
    enviar(provedor("nenhuma", usuario=""))

    assert [c[0] for c in smtp.chamadas] == ["conectar", "enviar", "sair"]


# --- Classificação dos erros ---


@pytest.mark.parametrize(
    ("erro", "esperado"),
    [
        (smtplib.SMTPRecipientsRefused({"a@x.com": (550, b"No such user")}), ErroEnvioPermanente),
        (smtplib.SMTPRecipientsRefused({"a@x.com": (450, b"Mailbox busy")}), ErroEnvioTemporario),
        (smtplib.SMTPSenderRefused(553, b"Sender rejected", "x@y.com"), ErroEnvioPermanente),
        (smtplib.SMTPDataError(554, b"Message rejected"), ErroEnvioPermanente),
        (smtplib.SMTPResponseException(421, b"Try later"), ErroEnvioTemporario),
        (smtplib.SMTPAuthenticationError(535, b"Bad credentials"), ErroEnvioTemporario),
        (smtplib.SMTPServerDisconnected("Connection unexpectedly closed"), ErroEnvioTemporario),
        (TimeoutError("timed out"), ErroEnvioTemporario),
        (ConnectionRefusedError("recusada"), ErroEnvioTemporario),
    ],
    ids=[
        "destinatario-recusado-5xx",
        "destinatario-recusado-4xx",
        "remetente-recusado",
        "mensagem-rejeitada",
        "servidor-ocupado-4xx",
        "credencial-recusada",
        "conexao-caiu",
        "tempo-esgotado",
        "conexao-recusada",
    ],
)
def test_classifica_o_erro_como_temporario_ou_permanente(smtp, erro, esperado):
    smtp.erro = erro

    with pytest.raises(esperado):
        enviar(provedor())


def test_mensagem_de_erro_traz_o_codigo_do_servidor_e_nunca_a_senha(smtp):
    smtp.erro = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    with pytest.raises(ErroEnvioTemporario) as falha:
        enviar(provedor())

    assert "535" in str(falha.value)
    assert "Username and Password not accepted" in str(falha.value)
    assert SENHA_SMTP not in str(falha.value)
    assert SENHA_SMTP not in repr(provedor())


def test_erro_longo_do_servidor_e_cortado_em_500_caracteres(smtp):
    smtp.erro = smtplib.SMTPResponseException(451, b"x" * 5000)

    with pytest.raises(ErroEnvioTemporario) as falha:
        enviar(provedor())

    assert len(str(falha.value)) <= 500


# --- Console e provedor falso ---


def test_console_registra_so_destinatario_e_assunto_e_nao_o_corpo(caplog):
    with caplog.at_level(logging.INFO, logger="app.integrations.email"):
        resultado = asyncio.run(ProvedorConsole().enviar(MENSAGEM))

    assert resultado is None
    assert "maria@example.com" in caplog.text and "Convite para participar" in caplog.text
    assert "Corpo em texto" not in caplog.text and "Corpo em HTML" not in caplog.text


def test_provedor_falso_guarda_as_mensagens_e_falha_na_ordem_programada():
    falso = ProvedorMemoria(falhas=[ErroEnvioTemporario("fora do ar"), None])

    with pytest.raises(ErroEnvioTemporario):
        asyncio.run(falso.enviar(MENSAGEM))
    assert falso.enviadas == []
    assert asyncio.run(falso.enviar(MENSAGEM)) == "memoria-1"
    assert falso.enviadas == [MENSAGEM]
    assert falso.tentativas == 2


# --- Escolha do provedor pelo ambiente ---


@pytest.fixture
def sem_provedor_em_cache():
    integracao.definir_provedor(None)
    yield
    integracao.definir_provedor(None)


def test_provedor_padrao_e_o_console(sem_provedor_em_cache, monkeypatch):
    monkeypatch.setattr(integracao.settings, "EMAIL_PROVIDER", "console")

    assert isinstance(integracao.obter_provedor(), ProvedorConsole)


def test_provedor_smtp_sai_das_variaveis_de_ambiente(sem_provedor_em_cache, monkeypatch):
    ambiente = integracao.settings
    monkeypatch.setattr(ambiente, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(ambiente, "SMTP_HOST", "smtp.exemplo.org")
    monkeypatch.setattr(ambiente, "SMTP_PORT", 465)
    monkeypatch.setattr(ambiente, "SMTP_USUARIO", "usuario")
    monkeypatch.setattr(ambiente, "SMTP_SENHA", SecretStr(SENHA_SMTP))
    monkeypatch.setattr(ambiente, "SMTP_SEGURANCA", "ssl")

    escolhido = integracao.obter_provedor()

    assert isinstance(escolhido, ProvedorSmtp)
    assert (escolhido.host, escolhido.porta, escolhido.usuario) == (
        "smtp.exemplo.org",
        465,
        "usuario",
    )
    assert escolhido.seguranca == "ssl"
    assert escolhido._senha == SENHA_SMTP


def test_provedor_definido_a_mao_tem_prioridade(sem_provedor_em_cache):
    falso = ProvedorMemoria()
    integracao.definir_provedor(falso)

    assert integracao.obter_provedor() is falso


def configuracao(**campos) -> Settings:
    return Settings(_env_file=None, JWT_SECRET="x" * 32, **campos)


def test_smtp_sem_servidor_impede_a_api_de_subir():
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        configuracao(EMAIL_PROVIDER="smtp", SMTP_HOST="")


def test_smtp_com_servidor_e_remetente_e_aceito():
    assert configuracao(EMAIL_PROVIDER="smtp", SMTP_HOST="smtp.exemplo.org").SMTP_PORT == 587


def test_provedor_desconhecido_e_recusado():
    with pytest.raises(ValidationError):
        configuracao(EMAIL_PROVIDER="sendgrid")


def test_senha_do_smtp_nao_aparece_na_representacao_da_configuracao():
    ambiente = configuracao(
        EMAIL_PROVIDER="smtp", SMTP_HOST="smtp.exemplo.org", SMTP_SENHA=SENHA_SMTP
    )

    assert SENHA_SMTP not in repr(ambiente)
    assert SENHA_SMTP not in str(ambiente.model_dump())
    assert ambiente.SMTP_SENHA.get_secret_value() == SENHA_SMTP
