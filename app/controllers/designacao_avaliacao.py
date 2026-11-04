from collections import defaultdict
from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, SituacaoConta, StatusProposta
from app.models import Avaliacao, DesignacaoAvaliacao, Submissao, Usuario


async def get_submissao_by_id(
    db: AsyncSession, submissao_id: UUID, *, para_atualizar: bool = False
) -> Submissao | None:
    consulta = select(Submissao).where(Submissao.id == submissao_id)
    if para_atualizar:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    return (await db.exec(consulta)).first()


async def listar_enviadas_do_hackathon(db: AsyncSession, hackathon_id: UUID) -> list[Submissao]:
    """Ordem fixa pelo id: a distribuição fica determinística."""
    consulta = (
        select(Submissao)
        .where(
            Submissao.hackathon_id == hackathon_id,
            Submissao.status == StatusProposta.ENVIADA,
        )
        .order_by(col(Submissao.id))
    )
    return list((await db.exec(consulta)).all())


async def listar_avaliadores_elegiveis(db: AsyncSession) -> list[Usuario]:
    """Comitê Científico com conta ativa (RF29). Não há vínculo avaliador-hackathon no banco."""
    consulta = (
        select(Usuario)
        .where(
            Usuario.papel == PapelUsuario.COMITE_CIENTIFICO,
            col(Usuario.ativo).is_(True),
            Usuario.situacao_conta == SituacaoConta.ATIVA,
        )
        .order_by(col(Usuario.id))
    )
    return list((await db.exec(consulta)).all())


async def contar_elegiveis_entre(db: AsyncSession, avaliador_ids: list[UUID]) -> int:
    consulta = select(func.count()).where(
        col(Usuario.id).in_(avaliador_ids),
        Usuario.papel == PapelUsuario.COMITE_CIENTIFICO,
        col(Usuario.ativo).is_(True),
        Usuario.situacao_conta == SituacaoConta.ATIVA,
    )
    return (await db.exec(consulta)).one()


async def listar_designacoes_do_hackathon(
    db: AsyncSession, hackathon_id: UUID
) -> list[DesignacaoAvaliacao]:
    consulta = (
        select(DesignacaoAvaliacao)
        .where(DesignacaoAvaliacao.hackathon_id == hackathon_id)
        .order_by(col(DesignacaoAvaliacao.atribuido_em), col(DesignacaoAvaliacao.id))
    )
    return list((await db.exec(consulta)).all())


async def listar_designacoes_da_submissao(
    db: AsyncSession, submissao_id: UUID
) -> list[DesignacaoAvaliacao]:
    consulta = select(DesignacaoAvaliacao).where(DesignacaoAvaliacao.submissao_id == submissao_id)
    return list((await db.exec(consulta)).all())


async def contar_carga_por_avaliador(db: AsyncSession, hackathon_id: UUID) -> dict[UUID, int]:
    consulta = (
        select(DesignacaoAvaliacao.avaliador_id, func.count())
        .where(DesignacaoAvaliacao.hackathon_id == hackathon_id)
        .group_by(DesignacaoAvaliacao.avaliador_id)
    )
    carga: dict[UUID, int] = defaultdict(int)
    for avaliador_id, total in (await db.exec(consulta)).all():
        carga[avaliador_id] = total
    return carga


async def submissoes_com_avaliacao(db: AsyncSession, submissao_ids: list[UUID]) -> set[UUID]:
    """Qualquer avaliação, inclusive rascunho sem nota final, impede redistribuição."""
    if not submissao_ids:
        return set()
    consulta = select(Avaliacao.submissao_id).where(col(Avaliacao.submissao_id).in_(submissao_ids))
    return set((await db.exec(consulta)).all())


async def listar_usuarios_por_id(db: AsyncSession, ids: list[UUID]) -> dict[UUID, Usuario]:
    if not ids:
        return {}
    consulta = select(Usuario).where(col(Usuario.id).in_(ids))
    return {usuario.id: usuario for usuario in (await db.exec(consulta)).all()}


def adicionar_designacao(db: AsyncSession, designacao: DesignacaoAvaliacao) -> None:
    db.add(designacao)


async def remover_designacao(db: AsyncSession, designacao: DesignacaoAvaliacao) -> None:
    await db.delete(designacao)


async def listar_submissoes_designadas(db: AsyncSession, avaliador_id: UUID) -> list[Submissao]:
    consulta = (
        select(Submissao)
        .join(DesignacaoAvaliacao, col(DesignacaoAvaliacao.submissao_id) == col(Submissao.id))
        .where(
            DesignacaoAvaliacao.avaliador_id == avaliador_id,
            Submissao.status == StatusProposta.ENVIADA,
        )
        .order_by(col(Submissao.enviado_em), col(Submissao.id))
    )
    return list((await db.exec(consulta)).all())


async def get_submissao_designada(
    db: AsyncSession, submissao_id: UUID, avaliador_id: UUID, *, somente_enviada: bool = True
) -> Submissao | None:
    consulta = (
        select(Submissao)
        .join(DesignacaoAvaliacao, col(DesignacaoAvaliacao.submissao_id) == col(Submissao.id))
        .where(
            Submissao.id == submissao_id,
            DesignacaoAvaliacao.avaliador_id == avaliador_id,
        )
    )
    if somente_enviada:
        consulta = consulta.where(Submissao.status == StatusProposta.ENVIADA)
    return (await db.exec(consulta)).first()
