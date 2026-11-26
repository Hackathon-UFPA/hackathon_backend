from uuid import UUID

from sqlalchemy.orm import defer
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoMarcoMentoria
from app.models import (
    AtribuicaoMentor,
    EntregaMentoria,
    HomologacaoResultado,
    MarcoMentoria,
    ResultadoProposta,
    Submissao,
    SubmissaoFinal,
)

ORDEM_CALENDARIO = (MarcoMentoria.data_limite, MarcoMentoria.ordem, MarcoMentoria.id)


async def ultimo_marco(
    db: AsyncSession, hackathon_id: UUID, tipo: TipoMarcoMentoria, excluir_id: UUID | None = None
) -> MarcoMentoria | None:
    consulta = (
        select(MarcoMentoria)
        .where(
            MarcoMentoria.hackathon_id == hackathon_id,
            MarcoMentoria.tipo == tipo,
        )
        .order_by(col(MarcoMentoria.data_limite).desc(), col(MarcoMentoria.ordem).desc())
        .limit(1)
    )
    if excluir_id is not None:
        consulta = consulta.where(MarcoMentoria.id != excluir_id)
    return (await db.exec(consulta)).first()


async def marco_tem_entregas(db: AsyncSession, marco_id: UUID) -> bool:
    consulta = select(EntregaMentoria.id).where(EntregaMentoria.marco_id == marco_id).limit(1)
    return (await db.exec(consulta)).first() is not None


async def mentor_acompanha_edicao(db: AsyncSession, mentor_id: UUID, hackathon_id: UUID) -> bool:
    consulta = (
        select(AtribuicaoMentor.id)
        .where(
            AtribuicaoMentor.mentor_id == mentor_id,
            AtribuicaoMentor.hackathon_id == hackathon_id,
            col(AtribuicaoMentor.encerrada_em).is_(None),
        )
        .limit(1)
    )
    return (await db.exec(consulta)).first() is not None


async def listar_entregas(
    db: AsyncSession, equipe_id: UUID, limite: int, deslocamento: int
) -> list[EntregaMentoria]:
    consulta = (
        select(EntregaMentoria)
        .where(EntregaMentoria.equipe_id == equipe_id, ~_tem_artefatos_finais())
        .order_by(col(EntregaMentoria.enviado_em).desc(), EntregaMentoria.id)
        .limit(limite)
        .offset(deslocamento)
    )
    return list((await db.exec(consulta)).all())


async def get_entrega(
    db: AsyncSession, equipe_id: UUID, entrega_id: UUID
) -> EntregaMentoria | None:
    consulta = select(EntregaMentoria).where(
        EntregaMentoria.equipe_id == equipe_id,
        EntregaMentoria.id == entrega_id,
        ~_tem_artefatos_finais(),
    )
    return (await db.exec(consulta)).first()


def _tem_artefatos_finais():
    return (
        select(SubmissaoFinal.entrega_id)
        .where(SubmissaoFinal.entrega_id == EntregaMentoria.id)
        .exists()
    )


def _propostas_aprovadas():
    return (
        select(ResultadoProposta.submissao_id)
        .join(HomologacaoResultado, HomologacaoResultado.id == ResultadoProposta.homologacao_id)
        .where(
            ResultadoProposta.hackathon_id == HomologacaoResultado.hackathon_id,
            col(ResultadoProposta.aprovada).is_(True),
        )
    )


async def proposta_aprovada_da_equipe(
    db: AsyncSession, equipe_id: UUID, hackathon_id: UUID
) -> UUID | None:
    consulta = (
        _propostas_aprovadas()
        .join(Submissao, Submissao.id == ResultadoProposta.submissao_id)
        .where(
            ResultadoProposta.equipe_id == equipe_id,
            ResultadoProposta.hackathon_id == hackathon_id,
            Submissao.equipe_id == equipe_id,
            Submissao.hackathon_id == hackathon_id,
        )
    )
    return (await db.exec(consulta)).first()


def submissao_final_habilitada_para_avaliacao():
    """Predicado para liberar artefatos e, na BE-S6-10, iniciar a avaliação."""
    return (
        _propostas_aprovadas()
        .where(
            ResultadoProposta.submissao_id == SubmissaoFinal.submissao_id,
            ResultadoProposta.equipe_id == SubmissaoFinal.equipe_id,
            ResultadoProposta.hackathon_id == SubmissaoFinal.hackathon_id,
        )
        .correlate(SubmissaoFinal)
        .exists()
    )


async def projetos_com_submissao_final(db: AsyncSession, hackathon_id: UUID) -> set[UUID]:
    consulta = select(SubmissaoFinal.submissao_id).where(
        SubmissaoFinal.hackathon_id == hackathon_id, submissao_final_habilitada_para_avaliacao()
    )
    return set((await db.exec(consulta)).all())


async def get_submissao_final(db: AsyncSession, equipe_id: UUID):
    consulta = (
        select(EntregaMentoria, SubmissaoFinal)
        .join(SubmissaoFinal, SubmissaoFinal.entrega_id == EntregaMentoria.id)
        .where(SubmissaoFinal.equipe_id == equipe_id)
        .options(defer(SubmissaoFinal.relatorio_pdf, raiseload=True))
    )
    return (await db.exec(consulta)).first()


async def get_relatorio_final(db: AsyncSession, equipe_id: UUID) -> bytes | None:
    consulta = select(SubmissaoFinal.relatorio_pdf).where(SubmissaoFinal.equipe_id == equipe_id)
    return (await db.exec(consulta)).first()
