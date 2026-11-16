"""Tokens de uso único enviados por e-mail (BE-S5-07): redefinição de senha e confirmação de
e-mail. O token é opaco e aleatório; o banco guarda só o SHA-256, como nos convites de mentor, e o
valor puro só existe no e-mail enviado."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FinalidadeToken
from app.controllers.token_usuario import get_token_por_hash, invalidar_tokens, salvar_token
from app.exceptions.auth import link_invalido
from app.models import TokenUsuario


def agora_utc() -> datetime:
    return datetime.now(UTC)


def hash_do_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def emitir(
    db: AsyncSession,
    usuario_id: UUID,
    finalidade: FinalidadeToken,
    validade_minutos: int,
    *,
    email: str | None = None,
) -> tuple[str, TokenUsuario]:
    """Gasta os tokens abertos da mesma finalidade (só o link mais novo vale), grava o novo e
    devolve o valor puro, que vai só no e-mail, junto com o registro. Sem commit: quem chama
    confirma a transação."""
    agora = agora_utc()
    await invalidar_tokens(db, usuario_id, finalidade, agora)
    token = secrets.token_urlsafe(32)
    registro = await salvar_token(
        db,
        TokenUsuario(
            usuario_id=usuario_id,
            finalidade=finalidade,
            token_hash=hash_do_token(token),
            email=email,
            expira_em=agora + timedelta(minutes=validade_minutos),
        ),
    )
    return token, registro


async def consumir(db: AsyncSession, token: str, finalidade: FinalidadeToken) -> TokenUsuario:
    """Acha o token, trava a linha e o marca como usado. Inexistente, vencido ou já usado dão a
    mesma resposta 400. A trava faz de dois usos simultâneos um sucesso e uma recusa.

    O token só fica gasto se quem chama confirmar a transação: em caso de erro depois daqui, o
    rollback devolve o link à pessoa."""
    registro = await get_token_por_hash(db, hash_do_token(token), finalidade, bloquear=True)
    if registro is None:
        link_invalido()
    # Depois de esperar a trava, a linha pode ter sido gasta pelo outro pedido
    await db.refresh(registro)
    agora = agora_utc()
    if registro.utilizado_em is not None or registro.expira_em <= agora:
        link_invalido()
    registro.utilizado_em = agora
    db.add(registro)
    return registro
