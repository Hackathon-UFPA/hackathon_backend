from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import AceiteTermo, Termo


async def listar_termos_vigentes(db: AsyncSession, hackathon_id: UUID) -> list[Termo]:
    """Uma versão vigente por tipo (índice único `uq_termos_vigente`)."""
    consulta = (
        select(Termo)
        .where(Termo.hackathon_id == hackathon_id, col(Termo.vigente).is_(True))
        .order_by(Termo.tipo)
    )
    return list((await db.exec(consulta)).all())


async def registrar_aceites(db: AsyncSession, usuario_id: UUID, termos_ids: list[UUID]) -> None:
    """Grava o aceite de cada versão de termo; a data e a hora vêm do banco (RF20).
    Aceitar de novo a mesma versão não duplica nem altera o registro original."""
    await db.exec(
        insert(AceiteTermo)
        .values([{"termo_id": termo_id, "usuario_id": usuario_id} for termo_id in termos_ids])
        .on_conflict_do_nothing(constraint="uq_aceites_termos_termo_usuario")
    )


async def listar_aceites(
    db: AsyncSession, usuario_id: UUID, termos_ids: list[UUID]
) -> list[AceiteTermo]:
    consulta = (
        select(AceiteTermo)
        .where(AceiteTermo.usuario_id == usuario_id, col(AceiteTermo.termo_id).in_(termos_ids))
        .order_by(AceiteTermo.aceito_em)
    )
    return list((await db.exec(consulta)).all())
