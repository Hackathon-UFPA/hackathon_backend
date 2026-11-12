from datetime import datetime
from uuid import UUID

from sqlalchemy import Text, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, StatusEmail
from app.models import ConviteMentor, EmailOutbox, Usuario


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


async def invalidar_convites(
    db: AsyncSession, mentor_id: UUID, agora: datetime, hackathon_id: UUID | None = None
) -> None:
    consulta = select(ConviteMentor.id).where(ConviteMentor.usuario_id == mentor_id)
    if hackathon_id is not None:
        consulta = consulta.where(ConviteMentor.hackathon_id == hackathon_id)
    ids = list((await db.exec(consulta)).all())
    if not ids:
        return
    # A trava do outbox também é mantida pelo worker durante o envio de convites de mentor.
    await db.exec(
        update(EmailOutbox)
        .where(
            col(EmailOutbox.chave_idempotencia).in_([f"convite-mentor:{id_}" for id_ in ids]),
            EmailOutbox.status != StatusEmail.ENVIADO,
            col(EmailOutbox.cancelado_em).is_(None),
        )
        .values(
            status=StatusEmail.FALHA,
            cancelado_em=agora,
            reservado_ate=None,
            corpo_texto=None,
            corpo_html=None,
            ultimo_erro="Convite de mentor revogado.",
            atualizado_em=agora,
        )
    )
    await db.exec(
        update(ConviteMentor)
        .where(col(ConviteMentor.id).in_(ids), col(ConviteMentor.utilizado_em).is_(None))
        .values(utilizado_em=agora)
    )


async def get_convite(db: AsyncSession, token_hash: str) -> ConviteMentor | None:
    return (
        await db.exec(select(ConviteMentor).where(ConviteMentor.token_hash == token_hash))
    ).first()


async def salvar_convite(db: AsyncSession, convite: ConviteMentor) -> None:
    db.add(convite)
    await db.flush()


async def listar_convites(db: AsyncSession, mentor_id: UUID, limite: int, deslocamento: int):
    return (
        await db.exec(
            select(ConviteMentor, EmailOutbox)
            .outerjoin(
                EmailOutbox,
                EmailOutbox.chave_idempotencia
                == "convite-mentor:" + col(ConviteMentor.id).cast(Text),
            )
            .where(ConviteMentor.usuario_id == mentor_id)
            .order_by(col(ConviteMentor.criado_em).desc(), ConviteMentor.id)
            .limit(limite)
            .offset(deslocamento)
        )
    ).all()
