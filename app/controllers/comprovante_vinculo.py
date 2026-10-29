from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusComprovante
from app.models import ComprovanteVinculo, Usuario


async def criar_comprovante(
    db: AsyncSession, comprovante: ComprovanteVinculo
) -> ComprovanteVinculo:
    """Só adiciona à sessão; quem chama decide quando confirmar a transação."""
    db.add(comprovante)
    await db.flush()
    return comprovante


async def get_comprovante_by_id(
    db: AsyncSession, comprovante_id: UUID, *, para_atualizar: bool = False
) -> ComprovanteVinculo | None:
    """Com `para_atualizar`, trava a linha: duas decisões sobre o mesmo comprovante não se
    misturam."""
    consulta = select(ComprovanteVinculo).where(ComprovanteVinculo.id == comprovante_id)
    if para_atualizar:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def listar_comprovantes(
    db: AsyncSession,
    *,
    status: StatusComprovante,
    hackathon_id: UUID | None,
    limite: int,
    deslocamento: int,
) -> list[tuple[ComprovanteVinculo, Usuario]]:
    """Fila de conferência: os mais antigos primeiro, com quem enviou."""
    consulta = (
        select(ComprovanteVinculo, Usuario)
        .join(Usuario, col(Usuario.id) == col(ComprovanteVinculo.usuario_id))
        .where(ComprovanteVinculo.status == status)
        .order_by(col(ComprovanteVinculo.enviado_em), col(ComprovanteVinculo.id))
        .limit(limite)
        .offset(deslocamento)
    )
    if hackathon_id is not None:
        consulta = consulta.where(ComprovanteVinculo.hackathon_id == hackathon_id)
    return [(c, u) for c, u in (await db.exec(consulta)).all()]


async def listar_comprovantes_do_usuario(
    db: AsyncSession, usuario_id: UUID
) -> list[ComprovanteVinculo]:
    consulta = (
        select(ComprovanteVinculo)
        .where(ComprovanteVinculo.usuario_id == usuario_id)
        .order_by(col(ComprovanteVinculo.enviado_em).desc(), col(ComprovanteVinculo.id))
    )
    return list((await db.exec(consulta)).all())


async def get_ultimo_comprovante(
    db: AsyncSession, usuario_id: UUID, hackathon_id: UUID
) -> ComprovanteVinculo | None:
    consulta = (
        select(ComprovanteVinculo)
        .where(
            ComprovanteVinculo.usuario_id == usuario_id,
            ComprovanteVinculo.hackathon_id == hackathon_id,
        )
        .order_by(col(ComprovanteVinculo.enviado_em).desc())
        .limit(1)
    )
    return (await db.exec(consulta)).first()


async def ultimo_comprovante_por_usuario(
    db: AsyncSession, hackathon_id: UUID, usuarios_ids: list[UUID]
) -> dict[UUID, ComprovanteVinculo]:
    """O comprovante mais recente de cada pessoa neste hackathon. Um reenvio depois de recusa
    é uma linha nova, então o último é o que vale."""
    consulta = (
        select(ComprovanteVinculo)
        .where(
            ComprovanteVinculo.hackathon_id == hackathon_id,
            col(ComprovanteVinculo.usuario_id).in_(usuarios_ids),
        )
        .order_by(col(ComprovanteVinculo.enviado_em).desc())
    )
    mais_recente: dict[UUID, ComprovanteVinculo] = {}
    for comprovante in (await db.exec(consulta)).all():
        mais_recente.setdefault(comprovante.usuario_id, comprovante)
    return mais_recente
