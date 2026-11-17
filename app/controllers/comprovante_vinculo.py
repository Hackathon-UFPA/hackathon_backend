from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusComprovante, TipoIntegrante
from app.models import ComprovanteVinculo, Hackathon, Usuario


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
    filtrar_organizacao: bool = False,
    organizacao_id: UUID | None = None,
) -> list[tuple[ComprovanteVinculo, Usuario]]:
    """Fila de conferência: os mais antigos primeiro, com quem enviou. Com
    `filtrar_organizacao`, só os comprovantes de hackathons da organização informada."""
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
    if filtrar_organizacao:
        consulta = consulta.join(
            Hackathon, col(Hackathon.id) == col(ComprovanteVinculo.hackathon_id)
        ).where(col(Hackathon.organizacao_id).is_not_distinct_from(organizacao_id))
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
    db: AsyncSession,
    usuario_id: UUID,
    hackathon_id: UUID,
    tipo_vinculo: TipoIntegrante | None = None,
) -> ComprovanteVinculo | None:
    """O mais recente da pessoa na edição; com `tipo_vinculo`, só entre os desse tipo."""
    consulta = select(ComprovanteVinculo).where(
        ComprovanteVinculo.usuario_id == usuario_id,
        ComprovanteVinculo.hackathon_id == hackathon_id,
    )
    if tipo_vinculo is not None:
        consulta = consulta.where(ComprovanteVinculo.tipo_vinculo == tipo_vinculo)
    consulta = consulta.order_by(col(ComprovanteVinculo.enviado_em).desc()).limit(1)
    return (await db.exec(consulta)).first()


async def ultimo_comprovante_por_usuario(
    db: AsyncSession,
    hackathon_id: UUID,
    usuarios_ids: list[UUID],
    tipos: dict[UUID, TipoIntegrante] | None = None,
) -> dict[UUID, ComprovanteVinculo]:
    """O comprovante mais recente de cada pessoa neste hackathon. Um reenvio depois de recusa
    é uma linha nova, então o último é o que vale. Com `tipos`, só vale o comprovante do vínculo
    que cada pessoa precisa comprovar (BE-S5-03): um comprovante de outro tipo não conta."""
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
        if tipos is not None and comprovante.tipo_vinculo != tipos.get(comprovante.usuario_id):
            continue
        mais_recente.setdefault(comprovante.usuario_id, comprovante)
    return mais_recente
