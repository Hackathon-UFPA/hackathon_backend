from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import MembroEquipe, Usuario
from app.schemas.membro_equipe import MembroEquipeUpdate
from app.utils.generic_db_operations import atualizar_instancia


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


async def listar_membros(db: AsyncSession, equipe_id: UUID) -> list[MembroEquipe]:
    consulta = (
        select(MembroEquipe)
        .where(MembroEquipe.equipe_id == equipe_id)
        .order_by(col(MembroEquipe.entrou_em).nulls_last(), col(MembroEquipe.usuario_id))
    )
    return list((await db.exec(consulta)).all())


async def atualizar_membro(
    db: AsyncSession, membro: MembroEquipe, dados: MembroEquipeUpdate
) -> MembroEquipe:
    """Sem commit: autorização e confirmação pertencem ao service."""
    await atualizar_instancia(membro, dados)
    db.add(membro)
    await db.flush()
    return membro


async def remover_membro(db: AsyncSession, membro: MembroEquipe) -> None:
    """Remove apenas o vínculo, preservando convites e aceites de termos."""
    await db.delete(membro)
    await db.flush()


async def listar_membros_com_usuario(
    db: AsyncSession, equipe_id: UUID
) -> list[tuple[MembroEquipe, Usuario]]:
    consulta = (
        select(MembroEquipe, Usuario)
        .join(Usuario, col(Usuario.id) == col(MembroEquipe.usuario_id))
        .where(MembroEquipe.equipe_id == equipe_id)
        .order_by(col(MembroEquipe.entrou_em).nulls_last(), col(MembroEquipe.usuario_id))
    )
    return [(membro, usuario) for membro, usuario in (await db.exec(consulta)).all()]
