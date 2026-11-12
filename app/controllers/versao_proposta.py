from uuid import UUID

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Avaliacao, DesignacaoAvaliacao, Protocolo, VersaoProposta


async def proximo_numero(db: AsyncSession, submissao_id: UUID) -> int:
    """Chamado com a proposta travada: o número não se repete (uq_versoes_proposta_numero)."""
    consulta = select(func.coalesce(func.max(VersaoProposta.numero), 0)).where(
        VersaoProposta.submissao_id == submissao_id
    )
    return (await db.exec(consulta)).one() + 1


async def criar_versao(db: AsyncSession, versao: VersaoProposta) -> VersaoProposta:
    db.add(versao)
    await db.flush()
    return versao


async def listar_versoes(
    db: AsyncSession, submissao_id: UUID
) -> list[tuple[VersaoProposta, Protocolo]]:
    """Da mais recente para a mais antiga, cada versão com o seu protocolo."""
    consulta = (
        select(VersaoProposta, Protocolo)
        .join(Protocolo, col(Protocolo.id) == col(VersaoProposta.protocolo_id))
        .where(VersaoProposta.submissao_id == submissao_id)
        .order_by(col(VersaoProposta.numero).desc())
    )
    return list((await db.exec(consulta)).all())


async def get_numero_da_versao(db: AsyncSession, protocolo_id: UUID) -> int | None:
    consulta = select(VersaoProposta.numero).where(VersaoProposta.protocolo_id == protocolo_id)
    return (await db.exec(consulta)).first()


async def proposta_foi_distribuida(db: AsyncSession, submissao_id: UUID) -> bool:
    consulta = select(DesignacaoAvaliacao.id).where(
        DesignacaoAvaliacao.submissao_id == submissao_id
    )
    return (await db.exec(consulta.limit(1))).first() is not None


async def proposta_tem_avaliacao(db: AsyncSession, submissao_id: UUID) -> bool:
    """Qualquer avaliação conta, inclusive rascunho e dado legado sem designação."""
    consulta = select(Avaliacao.id).where(Avaliacao.submissao_id == submissao_id)
    return (await db.exec(consulta.limit(1))).first() is not None
