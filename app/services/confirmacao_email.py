"""Envio do link de confirmação de e-mail (RF01, BE-S5-07)."""

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import FinalidadeToken, TipoEmail
from app.models import Usuario
from app.services.email import enfileirar, link_front
from app.services.token_usuario import emitir


async def enviar_confirmacao(db: AsyncSession, usuario: Usuario, email: str) -> None:
    """Emite o link que comprova a posse de `email` (o atual ou um novo, numa troca) e o
    enfileira. Sem commit: entra na transação de quem chama (cadastro, troca de e-mail...)."""
    token, registro = await emitir(
        db,
        usuario.id,
        FinalidadeToken.CONFIRMACAO_EMAIL,
        settings.EMAIL_CONFIRMACAO_MINUTOS,
        email=email,
    )
    await enfileirar(
        db,
        TipoEmail.CONFIRMACAO_EMAIL,
        destinatario_email=email,
        destinatario_nome=usuario.nome,
        usuario_id=usuario.id,
        contexto={
            "nome": usuario.nome or "participante",
            "link": link_front(f"/confirmar-email#token={token}"),
        },
        chave=f"confirmacao-email:{registro.id}",
    )
