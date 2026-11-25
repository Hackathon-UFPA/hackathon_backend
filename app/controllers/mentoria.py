from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoMarcoMentoria
from app.models import AtribuicaoMentor, EntregaMentoria, MarcoMentoria

ORDEM_CALENDARIO = (MarcoMentoria.data_limite, MarcoMentoria.ordem, MarcoMentoria.id)


async def ultimo_marco(
    db: AsyncSession, hackathon_id: UUID, tipo: TipoMarcoMentoria, excluir_id: UUID
) -> MarcoMentoria | None:
    consulta = (
        select(MarcoMentoria)
        .where(
            MarcoMentoria.hackathon_id == hackathon_id,
            MarcoMentoria.tipo == tipo,
            MarcoMentoria.id != excluir_id,
        )
        .order_by(col(MarcoMentoria.data_limite).desc(), col(MarcoMentoria.ordem).desc())
        .limit(1)
    )
    return (await db.exec(consulta)).first()


async def marco_tem_entregas(db: AsyncSession, marco_id: UUID) -> bool:
    consulta = select(EntregaMentoria.id).where(EntregaMentoria.marco_id == marco_id).limit(1)
    return (await db.exec(consulta)).first() is not None


async def mentor_acompanha_edicao(db: AsyncSession, mentor_id: UUID, hackathon_id: UUID) -> bool:
    consulta = (
        select(AtribuicaoMentor.id)
        .where(
            AtribuicaoMentor.mentor_id == mentor_id,
            AtribuicaoMentor.hackathon_id == hackathon_id,
            col(AtribuicaoMentor.encerrada_em).is_(None),
        )
        .limit(1)
    )
    return (await db.exec(consulta)).first() is not None


async def listar_entregas(
    db: AsyncSession, equipe_id: UUID, limite: int, deslocamento: int
) -> list[EntregaMentoria]:
    consulta = (
        select(EntregaMentoria)
        .where(EntregaMentoria.equipe_id == equipe_id)
        .order_by(col(EntregaMentoria.enviado_em).desc(), EntregaMentoria.id)
        .limit(limite)
        .offset(deslocamento)
    )
    return list((await db.exec(consulta)).all())


async def get_entrega(
    db: AsyncSession, equipe_id: UUID, entrega_id: UUID
) -> EntregaMentoria | None:
    consulta = select(EntregaMentoria).where(
        EntregaMentoria.equipe_id == equipe_id, EntregaMentoria.id == entrega_id
    )
    return (await db.exec(consulta)).first()
