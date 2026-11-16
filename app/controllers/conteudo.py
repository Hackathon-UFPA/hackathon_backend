"""Acesso ao banco do conteúdo institucional (BE-S5-12). Funções genéricas servem às tabelas que
têm `hackathon_id`: apoiadores, FAQ, fases do cronograma e sessões do treinamento."""

from uuid import UUID

from sqlalchemy import func
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import MaterialTreinamento


async def listar_itens[Item: SQLModel](
    db: AsyncSession,
    modelo: type[Item],
    hackathon_id: UUID,
    *,
    filtros: tuple = (),
    ordem: tuple = (),
    limite: int | None = None,
    deslocamento: int = 0,
) -> list[Item]:
    consulta = select(modelo).where(modelo.hackathon_id == hackathon_id, *filtros)
    consulta = consulta.order_by(*ordem)
    if limite is not None:
        consulta = consulta.limit(limite).offset(deslocamento)
    return list((await db.exec(consulta)).all())


async def get_item[Item: SQLModel](
    db: AsyncSession,
    modelo: type[Item],
    hackathon_id: UUID,
    item_id: UUID,
    *,
    bloquear: bool = False,
) -> Item | None:
    """O item só existe para a edição dele: um id de outra edição não é encontrado."""
    consulta = select(modelo).where(modelo.id == item_id, modelo.hackathon_id == hackathon_id)
    if bloquear:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def proxima_ordem[Item: SQLModel](
    db: AsyncSession, modelo: type[Item], hackathon_id: UUID
) -> int:
    """Próxima posição da lista. Só é seguro com a linha da edição travada (FOR UPDATE)."""
    consulta = select(func.coalesce(func.max(modelo.ordem), -1)).where(
        modelo.hackathon_id == hackathon_id
    )
    return (await db.exec(consulta)).one() + 1


async def salvar_item(db: AsyncSession, item: SQLModel) -> None:
    db.add(item)
    await db.flush()


async def remover_item(db: AsyncSession, item: SQLModel) -> None:
    await db.delete(item)
    await db.flush()


async def listar_materiais(
    db: AsyncSession, sessoes_ids: list[UUID]
) -> dict[UUID, list[MaterialTreinamento]]:
    """Materiais de várias sessões de uma vez, na ordem de cada sessão."""
    if not sessoes_ids:
        return {}
    consulta = (
        select(MaterialTreinamento)
        .where(col(MaterialTreinamento.sessao_id).in_(sessoes_ids))
        .order_by(MaterialTreinamento.ordem, MaterialTreinamento.criado_em, MaterialTreinamento.id)
    )
    materiais: dict[UUID, list[MaterialTreinamento]] = {}
    for material in (await db.exec(consulta)).all():
        materiais.setdefault(material.sessao_id, []).append(material)
    return materiais


async def get_material(
    db: AsyncSession, sessao_id: UUID, material_id: UUID
) -> MaterialTreinamento | None:
    consulta = select(MaterialTreinamento).where(
        MaterialTreinamento.id == material_id, MaterialTreinamento.sessao_id == sessao_id
    )
    return (await db.exec(consulta)).first()


async def proxima_ordem_material(db: AsyncSession, sessao_id: UUID) -> int:
    consulta = select(func.coalesce(func.max(MaterialTreinamento.ordem), -1)).where(
        MaterialTreinamento.sessao_id == sessao_id
    )
    return (await db.exec(consulta)).one() + 1
