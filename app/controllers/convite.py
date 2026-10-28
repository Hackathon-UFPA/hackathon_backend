from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusConvite
from app.exceptions.convite import convite_repetido
from app.exceptions.db import erro_de_integridade_sql
from app.models import Convite, Equipe


async def get_convite_by_id(
    db: AsyncSession, convite_id: UUID, *, para_atualizar: bool = False
) -> Convite | None:
    """Com `para_atualizar`, trava a linha: duas respostas ao mesmo convite não se misturam."""
    consulta = select(Convite).where(Convite.id == convite_id)
    if para_atualizar:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def listar_convites_da_equipe(db: AsyncSession, equipe_id: UUID) -> list[Convite]:
    consulta = (
        select(Convite).where(Convite.equipe_id == equipe_id).order_by(col(Convite.enviado_em))
    )
    return list((await db.exec(consulta)).all())


async def listar_pendentes_do_email(db: AsyncSession, email: str) -> list[tuple[Convite, Equipe]]:
    """Convites pendentes endereçados ao e-mail (sem diferenciar maiúsculas), com a equipe."""
    consulta = (
        select(Convite, Equipe)
        .join(Equipe, col(Equipe.id) == col(Convite.equipe_id))
        .where(func.lower(Convite.email) == email.lower(), Convite.status == StatusConvite.PENDENTE)
        .order_by(col(Convite.enviado_em).desc())
    )
    return [(convite, equipe) for convite, equipe in (await db.exec(consulta)).all()]


async def contar_pendentes(db: AsyncSession, equipe_id: UUID) -> int:
    consulta = (
        select(func.count())
        .select_from(Convite)
        .where(Convite.equipe_id == equipe_id, Convite.status == StatusConvite.PENDENTE)
    )
    return (await db.exec(consulta)).one()


async def criar_convite(db: AsyncSession, convite: Convite) -> Convite:
    """Só adiciona à sessão; quem chama decide quando confirmar a transação."""
    db.add(convite)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        # Índice único parcial: um convite em aberto ou aceito por e-mail em cada equipe
        if "uq_convites_equipe_email_ativo" in str(error.orig):
            convite_repetido()
        erro_de_integridade_sql(error)
    return convite
