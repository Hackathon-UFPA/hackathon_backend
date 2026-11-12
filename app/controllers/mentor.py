from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.models import ConviteMentor, Usuario


async def get_mentor(
    db: AsyncSession, mentor_id: UUID, *, bloquear: bool = False
) -> Usuario | None:
    consulta = select(Usuario).where(Usuario.id == mentor_id, Usuario.papel == PapelUsuario.MENTOR)
    if bloquear:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def listar_mentores(
    db: AsyncSession, ativo: bool | None, limite: int, deslocamento: int
) -> list[Usuario]:
    consulta = select(Usuario).where(Usuario.papel == PapelUsuario.MENTOR)
    if ativo is not None:
        consulta = consulta.where(Usuario.ativo == ativo)
    return list(
        (
            await db.exec(
                consulta.order_by(Usuario.email, Usuario.id).limit(limite).offset(deslocamento)
            )
        ).all()
    )


async def invalidar_convites(db: AsyncSession, mentor_id: UUID, agora: datetime) -> None:
    await db.exec(
        update(ConviteMentor)
        .where(ConviteMentor.usuario_id == mentor_id, col(ConviteMentor.utilizado_em).is_(None))
        .values(utilizado_em=agora)
    )


async def get_convite(db: AsyncSession, token_hash: str) -> ConviteMentor | None:
    return (
        await db.exec(select(ConviteMentor).where(ConviteMentor.token_hash == token_hash))
    ).first()


async def salvar_convite(db: AsyncSession, convite: ConviteMentor) -> None:
    db.add(convite)
    await db.flush()
