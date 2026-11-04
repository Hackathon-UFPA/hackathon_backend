from uuid import UUID

from sqlalchemy import and_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import RecomendacaoAvaliacao, StatusAvaliacao, StatusProposta
from app.models import (
    Avaliacao,
    DesignacaoAvaliacao,
    Equipe,
    HomologacaoResultado,
    ResultadoProposta,
    Submissao,
    Tema,
    Usuario,
)


async def get_homologacao(db: AsyncSession, hackathon_id: UUID) -> HomologacaoResultado | None:
    consulta = select(HomologacaoResultado).where(HomologacaoResultado.hackathon_id == hackathon_id)
    return (await db.exec(consulta)).first()


async def listar_propostas_com_equipe_e_tema(
    db: AsyncSession, hackathon_id: UUID
) -> list[tuple[Submissao, str | None, str | None]]:
    """Propostas ENVIADA do hackathon com o nome da equipe e o título do tema."""
    consulta = (
        select(Submissao, Equipe.nome, Tema.titulo)
        .join(Equipe, col(Equipe.id) == col(Submissao.equipe_id))
        .outerjoin(Tema, col(Tema.id) == col(Submissao.tema_id))
        .where(
            Submissao.hackathon_id == hackathon_id,
            Submissao.status == StatusProposta.ENVIADA,
        )
        .order_by(col(Submissao.id))
    )
    return list((await db.exec(consulta)).all())


async def listar_designacoes_com_avaliacao(
    db: AsyncSession, hackathon_id: UUID
) -> list[tuple[UUID, UUID, StatusAvaliacao | None, object, RecomendacaoAvaliacao | None]]:
    """Cada designação do hackathon com a avaliação do avaliador designado, se existir:
    (submissao_id, avaliador_id, status, nota, recomendacao)."""
    consulta = (
        select(
            DesignacaoAvaliacao.submissao_id,
            DesignacaoAvaliacao.avaliador_id,
            Avaliacao.status,
            Avaliacao.nota,
            Avaliacao.recomendacao,
        )
        .outerjoin(
            Avaliacao,
            and_(
                col(Avaliacao.submissao_id) == col(DesignacaoAvaliacao.submissao_id),
                col(Avaliacao.avaliador_id) == col(DesignacaoAvaliacao.avaliador_id),
            ),
        )
        .where(DesignacaoAvaliacao.hackathon_id == hackathon_id)
    )
    return list((await db.exec(consulta)).all())


async def listar_resultados(db: AsyncSession, homologacao_id: UUID) -> list[ResultadoProposta]:
    consulta = (
        select(ResultadoProposta)
        .where(ResultadoProposta.homologacao_id == homologacao_id)
        .order_by(col(ResultadoProposta.classificacao))
    )
    return list((await db.exec(consulta)).all())


async def listar_aprovadas(db: AsyncSession, homologacao_id: UUID) -> list[ResultadoProposta]:
    """Ordem alfabética pela equipe: a lista pública não revela a classificação."""
    consulta = (
        select(ResultadoProposta)
        .where(
            ResultadoProposta.homologacao_id == homologacao_id,
            col(ResultadoProposta.aprovada).is_(True),
        )
        .order_by(col(ResultadoProposta.equipe_nome).nulls_last(), col(ResultadoProposta.id))
    )
    return list((await db.exec(consulta)).all())


async def get_nome_usuario(db: AsyncSession, usuario_id: UUID) -> str | None:
    usuario = await db.get(Usuario, usuario_id)
    return (usuario.nome or usuario.email) if usuario else None


def adicionar_homologacao(
    db: AsyncSession, homologacao: HomologacaoResultado, resultados: list[ResultadoProposta]
) -> None:
    db.add(homologacao)
    db.add_all(resultados)
