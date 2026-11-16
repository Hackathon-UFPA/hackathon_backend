from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FinalidadeToken
from app.models import TokenUsuario


async def salvar_token(db: AsyncSession, token: TokenUsuario) -> TokenUsuario:
    db.add(token)
    await db.flush()
    return token


async def get_token_por_hash(
    db: AsyncSession,
    token_hash: str,
    finalidade: FinalidadeToken,
    *,
    bloquear: bool = False,
) -> TokenUsuario | None:
    """Com `bloquear`, trava a linha: dois usos simultâneos do mesmo token se enfileiram, e o
    segundo já o encontra gasto."""
    consulta = select(TokenUsuario).where(
        TokenUsuario.token_hash == token_hash, TokenUsuario.finalidade == finalidade
    )
    if bloquear:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def invalidar_tokens(
    db: AsyncSession, usuario_id: UUID, finalidade: FinalidadeToken, agora: datetime
) -> None:
    """Gasta os tokens ainda abertos: só o link mais recente continua valendo."""
    await db.exec(
        update(TokenUsuario)
        .where(
            TokenUsuario.usuario_id == usuario_id,
            TokenUsuario.finalidade == finalidade,
            col(TokenUsuario.utilizado_em).is_(None),
        )
        .values(utilizado_em=agora)
    )


async def existe_token_recente(
    db: AsyncSession, usuario_id: UUID, finalidade: FinalidadeToken, desde: datetime
) -> bool:
    """Há um token deste tipo criado depois de `desde`? Segura pedidos em sequência."""
    consulta = (
        select(TokenUsuario.id)
        .where(
            TokenUsuario.usuario_id == usuario_id,
            TokenUsuario.finalidade == finalidade,
            TokenUsuario.criado_em > desde,
        )
        .limit(1)
    )
    return (await db.exec(consulta)).first() is not None
