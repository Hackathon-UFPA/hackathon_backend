from uuid import UUID

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import MembroEquipe


async def get_membro(db: AsyncSession, equipe_id: UUID, usuario_id: UUID) -> MembroEquipe | None:
    return await db.get(MembroEquipe, (equipe_id, usuario_id))


async def get_membro_no_hackathon(
    db: AsyncSession, hackathon_id: UUID, usuario_id: UUID
) -> MembroEquipe | None:
    """Equipe da pessoa em um hackathon, se houver (RN02: só pode ter uma)."""
    consulta = select(MembroEquipe).where(
        MembroEquipe.hackathon_id == hackathon_id, MembroEquipe.usuario_id == usuario_id
    )
    return (await db.exec(consulta)).first()


async def contar_membros(db: AsyncSession, equipe_id: UUID) -> int:
    consulta = (
        select(func.count()).select_from(MembroEquipe).where(MembroEquipe.equipe_id == equipe_id)
    )
    return (await db.exec(consulta)).one()


def adicionar_membro(db: AsyncSession, membro: MembroEquipe) -> None:
    """Só adiciona à sessão; quem chama decide quando confirmar a transação."""
    db.add(membro)
