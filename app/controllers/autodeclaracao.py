from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import AutodeclaracaoVinculo, Usuario


async def travar_usuario(db: AsyncSession, usuario_id: UUID) -> None:
    """Serializa as declarações da mesma pessoa: duas iguais e simultâneas viram uma só."""
    await db.exec(select(Usuario.id).where(Usuario.id == usuario_id).with_for_update())


def criar_autodeclaracao(db: AsyncSession, declaracao: AutodeclaracaoVinculo) -> None:
    """Só adiciona à sessão; quem chama decide quando confirmar a transação."""
    db.add(declaracao)


async def listar_autodeclaracoes(
    db: AsyncSession, usuario_id: UUID, hackathon_id: UUID
) -> list[AutodeclaracaoVinculo]:
    """Da mais recente à mais antiga."""
    consulta = (
        select(AutodeclaracaoVinculo)
        .where(
            AutodeclaracaoVinculo.usuario_id == usuario_id,
            AutodeclaracaoVinculo.hackathon_id == hackathon_id,
        )
        .order_by(col(AutodeclaracaoVinculo.declarada_em).desc(), col(AutodeclaracaoVinculo.id))
    )
    return list((await db.exec(consulta)).all())


async def ultima_autodeclaracao_por_usuario(
    db: AsyncSession, hackathon_id: UUID, usuarios_ids: list[UUID]
) -> dict[UUID, AutodeclaracaoVinculo]:
    """A declaração mais recente de cada pessoa nesta edição."""
    consulta = (
        select(AutodeclaracaoVinculo)
        .where(
            AutodeclaracaoVinculo.hackathon_id == hackathon_id,
            col(AutodeclaracaoVinculo.usuario_id).in_(usuarios_ids),
        )
        .order_by(col(AutodeclaracaoVinculo.declarada_em).desc(), col(AutodeclaracaoVinculo.id))
    )
    mais_recente: dict[UUID, AutodeclaracaoVinculo] = {}
    for declaracao in (await db.exec(consulta)).all():
        mais_recente.setdefault(declaracao.usuario_id, declaracao)
    return mais_recente


async def get_autodeclaracoes_por_id(
    db: AsyncSession, ids: list[UUID]
) -> dict[UUID, AutodeclaracaoVinculo]:
    if not ids:
        return {}
    consulta = select(AutodeclaracaoVinculo).where(col(AutodeclaracaoVinculo.id).in_(ids))
    return {d.id: d for d in (await db.exec(consulta)).all()}
