from uuid import UUID

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Avaliacao, NotaCriterioAvaliacao


async def get_minha_avaliacao(
    db: AsyncSession, submissao_id: UUID, avaliador_id: UUID
) -> Avaliacao | None:
    consulta = select(Avaliacao).where(
        Avaliacao.submissao_id == submissao_id, Avaliacao.avaliador_id == avaliador_id
    )
    return (await db.exec(consulta)).first()


async def listar_notas(db: AsyncSession, avaliacao_id: UUID) -> list[NotaCriterioAvaliacao]:
    consulta = (
        select(NotaCriterioAvaliacao)
        .where(NotaCriterioAvaliacao.avaliacao_id == avaliacao_id)
        .order_by(NotaCriterioAvaliacao.criterio_id)
    )
    return list((await db.exec(consulta)).all())


async def salvar_avaliacao(db: AsyncSession, avaliacao: Avaliacao) -> None:
    db.add(avaliacao)
    await db.flush()


async def substituir_notas(
    db: AsyncSession, avaliacao_id: UUID, notas: list[NotaCriterioAvaliacao]
) -> None:
    await db.exec(
        delete(NotaCriterioAvaliacao).where(NotaCriterioAvaliacao.avaliacao_id == avaliacao_id)
    )
    db.add_all(notas)
    await db.flush()
