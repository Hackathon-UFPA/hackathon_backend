from uuid import UUID

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FaseRubrica
from app.models import CriterioRubrica, Hackathon, Rubrica


async def get_hackathon_para_atualizar(db: AsyncSession, hackathon_id: UUID) -> Hackathon | None:
    """Trava a edição (FOR NO KEY UPDATE) para serializar alterações e publicação da rubrica
    sem bloquear inserções que só referenciam o hackathon."""
    consulta = select(Hackathon).where(Hackathon.id == hackathon_id).with_for_update(key_share=True)
    return (await db.exec(consulta)).first()


async def get_rubrica_do_hackathon(
    db: AsyncSession, hackathon_id: UUID, fase: FaseRubrica = FaseRubrica.PROPOSTA
) -> Rubrica | None:
    consulta = select(Rubrica).where(Rubrica.hackathon_id == hackathon_id, Rubrica.fase == fase)
    return (await db.exec(consulta)).first()


async def listar_criterios(db: AsyncSession, rubrica_id: UUID) -> list[CriterioRubrica]:
    consulta = (
        select(CriterioRubrica)
        .where(CriterioRubrica.rubrica_id == rubrica_id)
        .order_by(CriterioRubrica.ordem)
    )
    return list((await db.exec(consulta)).all())


async def salvar_rubrica(db: AsyncSession, rubrica: Rubrica) -> Rubrica:
    db.add(rubrica)
    await db.flush()
    return rubrica


async def substituir_criterios(
    db: AsyncSession, rubrica_id: UUID, criterios: list[CriterioRubrica]
) -> None:
    await db.exec(delete(CriterioRubrica).where(CriterioRubrica.rubrica_id == rubrica_id))
    db.add_all(criterios)
    await db.flush()
