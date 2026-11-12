"""Provedores de envio de e-mail (RNF28).

O resto do sistema nunca fala com o provedor: grava o e-mail na fila (`app.services.email`) e o
worker (`app.jobs.email`) entrega pelo provedor configurado em `EMAIL_PROVIDER`.

- `console`: só registra destinatário e assunto no log. Padrão em desenvolvimento, nada sai.
- `smtp`: envia por SMTP. Host, porta e credenciais vêm só de variáveis de ambiente.
- `ProvedorMemoria`: provedor falso para testes; guarda as mensagens e falha sob comando.

Todo provedor devolve o id da mensagem (ou None) e, quando falha, levanta `ErroEnvioTemporario`
(o worker tenta de novo) ou `ErroEnvioPermanente` (o worker desiste). As mensagens de erro
nunca trazem senha nem o conteúdo do e-mail.
"""

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

from app.const.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MensagemEmail:
    destinatario: str
    destinatario_nome: str | None
    assunto: str
    texto: str
    html: str


class ErroEnvio(Exception):
    """Base dos erros de envio. A mensagem vai para `emails_outbox.ultimo_erro`."""


class ErroEnvioTemporario(ErroEnvio):
    """Pode dar certo depois: servidor fora do ar, tempo esgotado, limite de envio, credencial."""


class ErroEnvioPermanente(ErroEnvio):
    """Não adianta repetir: destinatário recusado, remetente recusado, mensagem rejeitada."""


class ProvedorEmail(Protocol):
    nome: str

    async def enviar(self, mensagem: MensagemEmail) -> str | None: ...


class ProvedorConsole:
    nome = "console"

    async def enviar(self, mensagem: MensagemEmail) -> str | None:
        logger.info("E-mail (console) para %s: %s", mensagem.destinatario, mensagem.assunto)
        return None


@dataclass
class ProvedorMemoria:
    """Provedor falso: guarda o que seria enviado. `falhas` é uma fila de erros, um por envio,
    na ordem das chamadas (None deixa o envio passar)."""

    nome = "memoria"
    enviadas: list[MensagemEmail] = field(default_factory=list)
    falhas: list[ErroEnvio | Exception | None] = field(default_factory=list)
    tentativas: int = 0

    async def enviar(self, mensagem: MensagemEmail) -> str | None:
        self.tentativas += 1
        if self.falhas:
            falha = self.falhas.pop(0)
            if falha is not None:
                raise falha
        self.enviadas.append(mensagem)
        return f"memoria-{len(self.enviadas)}"


def _descrever(erro: Exception) -> str:
    """Resumo curto e seguro do erro: classe, código e resposta do servidor, nunca credenciais."""
    codigo = getattr(erro, "smtp_code", None)
    resposta = getattr(erro, "smtp_error", None)
    if isinstance(resposta, bytes):
        resposta = resposta.decode("utf-8", "replace")
    partes = [type(erro).__name__]
    if codigo:
        partes.append(str(codigo))
    if resposta:
        partes.append(str(resposta))
    elif not codigo and str(erro):
        partes.append(str(erro))
    return " ".join(partes)[:500]


class ProvedorSmtp:
    nome = "smtp"

    def __init__(
        self,
        *,
        host: str,
        porta: int,
        usuario: str,
        senha: str,
        seguranca: str,
        timeout: int,
        remetente_nome: str,
        remetente_endereco: str,
    ):
        self.host = host
        self.porta = porta
        self.usuario = usuario
        self._senha = senha
        self.seguranca = seguranca
        self.timeout = timeout
        self.remetente_nome = remetente_nome
        self.remetente_endereco = remetente_endereco

    def __repr__(self) -> str:
        return f"ProvedorSmtp(host={self.host!r}, porta={self.porta})"

    def montar(self, mensagem: MensagemEmail) -> EmailMessage:
        """Texto simples com alternativa HTML. Quebra de linha em endereço ou assunto é recusada
        pela própria biblioteca (ValueError), o que impede injeção de cabeçalhos."""
        email = EmailMessage()
        email["From"] = formataddr((self.remetente_nome, self.remetente_endereco))
        email["To"] = formataddr((mensagem.destinatario_nome or "", mensagem.destinatario))
        email["Subject"] = mensagem.assunto
        email["Message-ID"] = make_msgid(domain=self.remetente_endereco.rpartition("@")[2])
        email["Auto-Submitted"] = "auto-generated"
        email.set_content(mensagem.texto)
        email.add_alternative(mensagem.html, subtype="html")
        return email

    def _enviar_sincrono(self, email: EmailMessage) -> None:
        contexto = ssl.create_default_context()
        if self.seguranca == "ssl":
            cliente = smtplib.SMTP_SSL(
                self.host, self.porta, timeout=self.timeout, context=contexto
            )
        else:
            cliente = smtplib.SMTP(self.host, self.porta, timeout=self.timeout)
        with cliente:
            if self.seguranca == "starttls":
                cliente.starttls(context=contexto)
            if self.usuario:
                cliente.login(self.usuario, self._senha)
            cliente.send_message(email)

    async def enviar(self, mensagem: MensagemEmail) -> str | None:
        try:
            email = self.montar(mensagem)
        except ValueError as erro:
            raise ErroEnvioPermanente(f"Mensagem inválida: {erro}"[:500]) from erro
        try:
            await asyncio.to_thread(self._enviar_sincrono, email)
        except smtplib.SMTPRecipientsRefused as erro:
            codigos = [codigo for codigo, _ in erro.recipients.values()]
            if codigos and all(400 <= c < 500 for c in codigos):
                raise ErroEnvioTemporario(_descrever(erro)) from erro
            raise ErroEnvioPermanente(f"Destinatário recusado ({_descrever(erro)})") from erro
        except smtplib.SMTPAuthenticationError as erro:
            # Credencial errada se corrige no ambiente: o e-mail espera na fila, não se perde
            raise ErroEnvioTemporario(_descrever(erro)) from erro
        except smtplib.SMTPResponseException as erro:
            if 500 <= erro.smtp_code < 600:
                raise ErroEnvioPermanente(_descrever(erro)) from erro
            raise ErroEnvioTemporario(_descrever(erro)) from erro
        except (smtplib.SMTPException, OSError) as erro:
            raise ErroEnvioTemporario(_descrever(erro)) from erro
        return str(email["Message-ID"])


_provedor: ProvedorEmail | None = None


def definir_provedor(provedor: ProvedorEmail | None) -> None:
    """Troca o provedor em uso (testes). None volta ao que está configurado no ambiente."""
    global _provedor
    _provedor = provedor


def obter_provedor() -> ProvedorEmail:
    global _provedor
    if _provedor is None:
        if settings.EMAIL_PROVIDER == "smtp":
            _provedor = ProvedorSmtp(
                host=settings.SMTP_HOST,
                porta=settings.SMTP_PORT,
                usuario=settings.SMTP_USUARIO,
                senha=settings.SMTP_SENHA.get_secret_value(),
                seguranca=settings.SMTP_SEGURANCA,
                timeout=settings.SMTP_TIMEOUT_SEGUNDOS,
                remetente_nome=settings.EMAIL_REMETENTE_NOME,
                remetente_endereco=settings.EMAIL_REMETENTE_ENDERECO,
            )
        else:
            _provedor = ProvedorConsole()
    return _provedor
