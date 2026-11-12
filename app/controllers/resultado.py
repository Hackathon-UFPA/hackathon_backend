from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import RecomendacaoAvaliacao, StatusAvaliacao, StatusProposta
from app.models import (
    Avaliacao,
    DesignacaoAvaliacao,
    Equipe,
    HomologacaoResultado,
    NotaCriterioAvaliacao,
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


@dataclass(frozen=True)
class DesignacaoComAvaliacao:
    """Uma designação do hackathon com a avaliação do avaliador designado, se existir."""

    submissao_id: UUID
    avaliador_id: UUID
    status: StatusAvaliacao | None
    nota: Decimal | None
    recomendacao: RecomendacaoAvaliacao | None
    parecer: str | None
    rubrica_id: UUID | None
    notas_por_criterio: int


async def listar_designacoes_com_avaliacao(
    db: AsyncSession, hackathon_id: UUID
) -> list[DesignacaoComAvaliacao]:
    notas = (
        select(func.count())
        .select_from(NotaCriterioAvaliacao)
        .where(col(NotaCriterioAvaliacao.avaliacao_id) == col(Avaliacao.id))
        .scalar_subquery()
    )
    consulta = (
        select(
            DesignacaoAvaliacao.submissao_id,
            DesignacaoAvaliacao.avaliador_id,
            Avaliacao.status,
            Avaliacao.nota,
            Avaliacao.recomendacao,
            Avaliacao.comentarios,
            Avaliacao.rubrica_id,
            notas,
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
    return [
        DesignacaoComAvaliacao(*linha[:7], notas_por_criterio=linha[7] or 0)
        for linha in (await db.exec(consulta)).all()
    ]


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


async def equipe_reprovada(db: AsyncSession, equipe_id: UUID) -> bool:
    """RF34: a equipe tem proposta com resultado homologado e `aprovada = false`."""
    consulta = (
        select(ResultadoProposta.id)
        .where(
            ResultadoProposta.equipe_id == equipe_id,
            col(ResultadoProposta.aprovada).is_(False),
        )
        .limit(1)
    )
    return (await db.exec(consulta)).first() is not None


async def get_resultado_da_equipe(
    db: AsyncSession, homologacao_id: UUID, equipe_id: UUID
) -> ResultadoProposta | None:
    consulta = select(ResultadoProposta).where(
        ResultadoProposta.homologacao_id == homologacao_id,
        ResultadoProposta.equipe_id == equipe_id,
    )
    return (await db.exec(consulta)).first()


async def listar_pareceres(db: AsyncSession, submissao_id: UUID) -> list[Avaliacao]:
    """Avaliações ENVIADA da proposta, em ordem estável que não revela o avaliador."""
    consulta = (
        select(Avaliacao)
        .where(
            Avaliacao.submissao_id == submissao_id,
            Avaliacao.status == StatusAvaliacao.ENVIADA,
        )
        .order_by(col(Avaliacao.id))
    )
    return list((await db.exec(consulta)).all())
