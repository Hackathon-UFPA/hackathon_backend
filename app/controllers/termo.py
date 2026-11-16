from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoTermo
from app.models import AceiteTermo, Termo


async def listar_termos_vigentes(db: AsyncSession, hackathon_id: UUID) -> list[Termo]:
    """Uma versão vigente por tipo (índice único `uq_termos_vigente`)."""
    consulta = (
        select(Termo)
        .where(Termo.hackathon_id == hackathon_id, col(Termo.vigente).is_(True))
        .order_by(Termo.tipo)
    )
    return list((await db.exec(consulta)).all())


async def listar_termos(
    db: AsyncSession,
    hackathon_id: UUID,
    *,
    tipo: TipoTermo | None,
    rascunho: bool | None,
    limite: int,
    deslocamento: int,
) -> list[Termo]:
    """Todas as versões, das mais novas para as mais antigas (BE-S5-12)."""
    consulta = select(Termo).where(Termo.hackathon_id == hackathon_id)
    if tipo is not None:
        consulta = consulta.where(Termo.tipo == tipo)
    if rascunho is not None:
        consulta = consulta.where(Termo.rascunho == rascunho)
    consulta = consulta.order_by(
        Termo.tipo, col(Termo.publicado_em).desc().nulls_first(), Termo.versao, Termo.id
    )
    return list((await db.exec(consulta.limit(limite).offset(deslocamento))).all())


async def get_termo(
    db: AsyncSession, hackathon_id: UUID, termo_id: UUID, *, bloquear: bool = False
) -> Termo | None:
    consulta = select(Termo).where(Termo.id == termo_id, Termo.hackathon_id == hackathon_id)
    if bloquear:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def get_termo_vigente(db: AsyncSession, hackathon_id: UUID, tipo: TipoTermo) -> Termo | None:
    consulta = select(Termo).where(
        Termo.hackathon_id == hackathon_id, Termo.tipo == tipo, col(Termo.vigente).is_(True)
    )
    return (await db.exec(consulta)).first()


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


async def listar_aceites_dos_usuarios(
    db: AsyncSession, usuarios_ids: list[UUID], termos_ids: set[UUID]
) -> dict[UUID, set[UUID]]:
    """Quais das versões `termos_ids` cada pessoa aceitou."""
    consulta = select(AceiteTermo.usuario_id, AceiteTermo.termo_id).where(
        col(AceiteTermo.usuario_id).in_(usuarios_ids),
        col(AceiteTermo.termo_id).in_(termos_ids),
    )
    aceites: dict[UUID, set[UUID]] = {}
    for usuario_id, termo_id in (await db.exec(consulta)).all():
        aceites.setdefault(usuario_id, set()).add(termo_id)
    return aceites
