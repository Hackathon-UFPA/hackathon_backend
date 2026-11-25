"""Consultas do painel do mentor (RF41). A autorização está no próprio filtro de
`equipes_acompanhadas`: o que ela não devolve não pode aparecer no painel."""

from uuid import UUID

from sqlalchemy import exists
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import SituacaoEquipe
from app.controllers.mentoria import ORDEM_CALENDARIO
from app.models import (
    AtribuicaoMentor,
    EntregaMentoria,
    Equipe,
    Hackathon,
    MarcoMentoria,
    ResultadoProposta,
)


async def equipes_acompanhadas(
    db: AsyncSession,
    mentor_id: UUID,
    organizacao_id: UUID | None,
    *,
    hackathon_id: UUID | None = None,
    equipe_id: UUID | None = None,
) -> list[tuple[AtribuicaoMentor, Equipe, Hackathon]]:
    """Equipes com atribuição vigente a este mentor, homologadas, com proposta aprovada e em
    edição da organização dele (RN16). Vínculo substituído ou encerrado não entra.

    Não pagina no banco: o resumo do painel precisa de todas, e a quantidade de vínculos
    vigentes já é limitada pela capacidade do mentor (`usuarios.max_equipes`)."""
    proposta_aprovada = exists().where(
        col(ResultadoProposta.equipe_id) == col(Equipe.id),
        col(ResultadoProposta.hackathon_id) == col(Equipe.hackathon_id),
        col(ResultadoProposta.aprovada).is_(True),
    )
    consulta = (
        select(AtribuicaoMentor, Equipe, Hackathon)
        .join(Equipe, col(Equipe.id) == col(AtribuicaoMentor.equipe_id))
        .join(Hackathon, col(Hackathon.id) == col(Equipe.hackathon_id))
        .where(
            AtribuicaoMentor.mentor_id == mentor_id,
            col(AtribuicaoMentor.encerrada_em).is_(None),
            Equipe.situacao == SituacaoEquipe.HOMOLOGADA,
            proposta_aprovada,
            col(Hackathon.organizacao_id).is_not_distinct_from(organizacao_id),
        )
        .order_by(col(Hackathon.nome), col(Equipe.nome), col(Equipe.id))
    )
    if hackathon_id is not None:
        consulta = consulta.where(Equipe.hackathon_id == hackathon_id)
    if equipe_id is not None:
        consulta = consulta.where(Equipe.id == equipe_id)
    return list((await db.exec(consulta)).all())


async def marcos_das_edicoes(db: AsyncSession, hackathon_ids: set[UUID]) -> list[MarcoMentoria]:
    consulta = (
        select(MarcoMentoria)
        .where(col(MarcoMentoria.hackathon_id).in_(hackathon_ids))
        .order_by(*ORDEM_CALENDARIO)
    )
    return list((await db.exec(consulta)).all())


async def entregas_das_equipes(db: AsyncSession, equipe_ids: set[UUID]) -> list[EntregaMentoria]:
    consulta = select(EntregaMentoria).where(col(EntregaMentoria.equipe_id).in_(equipe_ids))
    return list((await db.exec(consulta)).all())
