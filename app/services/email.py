"""Fila de e-mails transacionais (RNF28, RF60).

Quem precisa avisar alguém chama `enfileirar` dentro da transação da própria ação: o e-mail fica
gravado junto com ela e só existe se ela for confirmada. O envio é feito depois pelo worker
(`app.services.email_envio`), então uma falha do provedor nunca desfaz a ação principal.

Para um fluxo novo (ex.: recuperação de senha), basta:

    await enfileirar(
        db, TipoEmail.RECUPERACAO_SENHA,
        destinatario_email=usuario.email, destinatario_nome=usuario.nome, usuario_id=usuario.id,
        contexto={"nome": usuario.nome, "link": link_front(f"/redefinir-senha?token={token}"),
                  "validade_minutos": 30},
        chave=f"recuperacao:{pedido.id}",
    )
"""

import logging
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import StatusEmail, TipoEmail
from app.controllers.email_outbox import (
    adicionar_email,
    get_email,
    listar_emails,
    recolocar_na_fila,
)
from app.exceptions.email import email_cancelado, email_nao_encontrado, reenvio_nao_permitido
from app.models import EmailOutbox
from app.services.email_template import renderizar

logger = logging.getLogger(__name__)


def link_front(caminho: str) -> str:
    """Endereço de uma página do front (`FRONTEND_URL`), para o botão do e-mail."""
    return f"{settings.FRONTEND_URL.rstrip('/')}/{caminho.lstrip('/')}"


def _validar_destinatario(email: str) -> str:
    email = email.strip()
    if not email or "@" not in email[1:] or any(ord(c) < 32 or ord(c) == 127 for c in email):
        raise ValueError("Destinatário inválido para e-mail.")
    return email


async def enfileirar(
    db: AsyncSession,
    tipo: TipoEmail,
    *,
    destinatario_email: str,
    contexto: dict,
    destinatario_nome: str | None = None,
    usuario_id: UUID | None = None,
    chave: str | None = None,
) -> bool:
    """Grava o e-mail na fila, sem commit. Devolve True se gravou.

    `chave` evita avisos repetidos: com a mesma chave a segunda gravação é ignorada (False).
    Quando não dá para enfileirar (destinatário inválido, template quebrado, erro no banco), o
    problema vai para o log e a ação principal segue: um aviso não pode derrubá-la. A gravação
    roda num savepoint, então um erro dela não invalida a transação de quem chamou.
    """
    try:
        destinatario = _validar_destinatario(destinatario_email)
        renderizado = renderizar(tipo, contexto)
        async with db.begin_nested():
            email_id = await adicionar_email(
                db,
                {
                    "tipo": tipo,
                    "destinatario_email": destinatario,
                    "destinatario_nome": destinatario_nome,
                    "usuario_id": usuario_id,
                    "assunto": renderizado.assunto,
                    "corpo_texto": renderizado.texto,
                    "corpo_html": renderizado.html,
                    "chave_idempotencia": chave,
                    "max_tentativas": settings.EMAIL_MAX_TENTATIVAS,
                },
            )
    except Exception as falha:
        if (chave or "").startswith("convite-mentor:"):
            # Exceções SQL/template podem conter parâmetros com o link secreto do convite.
            logger.error(
                "Não foi possível enfileirar o e-mail %s para o usuário %s (%s)",
                tipo,
                usuario_id,
                type(falha).__name__,
            )
        else:
            logger.exception(
                "Não foi possível enfileirar o e-mail %s para o usuário %s", tipo, usuario_id
            )
        return False
    return email_id is not None


async def listar(
    db: AsyncSession,
    *,
    status: StatusEmail | None,
    tipo: TipoEmail | None,
    destinatario: str | None,
    limite: int,
    deslocamento: int,
) -> list[EmailOutbox]:
    return await listar_emails(
        db,
        status=status,
        tipo=tipo,
        destinatario=destinatario,
        limite=limite,
        deslocamento=deslocamento,
    )


async def consultar(db: AsyncSession, email_id: UUID) -> EmailOutbox:
    email = await get_email(db, email_id)
    if email is None:
        email_nao_encontrado()
    return email


async def reenviar(db: AsyncSession, email_id: UUID) -> EmailOutbox:
    """Devolve à fila um e-mail em FALHA, com as tentativas zeradas. Os demais estados já estão
    na fila ou já foram entregues, então reenviar seria duplicar o aviso."""
    email = await get_email(db, email_id, para_atualizar=True)
    if email is None:
        email_nao_encontrado()
    if email.cancelado_em is not None:
        email_cancelado()
    if email.status != StatusEmail.FALHA:
        reenvio_nao_permitido(email.status)
    await recolocar_na_fila(db, email)
    await db.commit()
    return email
