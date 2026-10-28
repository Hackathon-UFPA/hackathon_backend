from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Equipe, Hackathon


async def get_equipe_by_id(
    db: AsyncSession, equipe_id: UUID, *, para_atualizar: bool = False
) -> Equipe | None:
    """Com `para_atualizar`, trava a linha até o fim da transação: serve para contar vagas sem
    que dois aceites simultâneos estourem o limite da equipe."""
    consulta = select(Equipe).where(Equipe.id == equipe_id)
    if para_atualizar:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def get_hackathon_by_id(db: AsyncSession, hackathon_id: UUID) -> Hackathon | None:
    return await db.get(Hackathon, hackathon_id)
