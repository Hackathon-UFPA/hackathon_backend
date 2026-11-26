"""Consultas dos feedbacks do mentor (RF40) e do histórico unificado da mentoria (RF42)."""

from uuid import UUID

from sqlalchemy import exists, literal_column, union_all
from sqlalchemy.orm import aliased
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.controllers.mentoria import tem_artefatos_finais
from app.models import AtribuicaoMentor, EntregaMentoria, FeedbackMentoria, Usuario

# Feedback, nome do autor e id do feedback que o corrigiu (se houver).
LinhaFeedback = tuple[FeedbackMentoria, str | None, UUID | None]


def _com_autor_e_correcao():
    corretor = aliased(FeedbackMentoria)
    return (
        select(FeedbackMentoria, Usuario.nome, corretor.id)
        .join(Usuario, col(Usuario.id) == col(FeedbackMentoria.autor_id))
        .outerjoin(corretor, col(corretor.corrige_id) == col(FeedbackMentoria.id))
    )


async def get_por_chave(db: AsyncSession, autor_id: UUID, chave: str) -> LinhaFeedback | None:
    consulta = _com_autor_e_correcao().where(
        FeedbackMentoria.autor_id == autor_id, FeedbackMentoria.chave_idempotencia == chave
    )
    return (await db.exec(consulta)).first()


async def get_da_equipe(
    db: AsyncSession, equipe_id: UUID, feedback_id: UUID
) -> LinhaFeedback | None:
    consulta = _com_autor_e_correcao().where(
        FeedbackMentoria.equipe_id == equipe_id, FeedbackMentoria.id == feedback_id
    )
    return (await db.exec(consulta)).first()


async def listar(
    db: AsyncSession, equipe_id: UUID, limite: int, deslocamento: int
) -> list[LinhaFeedback]:
    consulta = (
        _com_autor_e_correcao()
        .where(FeedbackMentoria.equipe_id == equipe_id)
        .order_by(col(FeedbackMentoria.criado_em).desc(), FeedbackMentoria.id)
        .limit(limite)
        .offset(deslocamento)
    )
    return list((await db.exec(consulta)).all())


async def historico(
    db: AsyncSession, equipe_id: UUID, limite: int, deslocamento: int
) -> list[tuple[str, UUID]]:
    """Posição de cada item da linha do tempo (tipo e id): entregas e feedbacks juntos, do mais
    recente ao mais antigo, paginados no banco. A submissão final tem artefatos próprios e fica
    fora, como na listagem de entregas."""
    entregas = select(
        literal_column("'ENTREGA'").label("tipo"),
        col(EntregaMentoria.id).label("id"),
        col(EntregaMentoria.enviado_em).label("ocorrido_em"),
    ).where(EntregaMentoria.equipe_id == equipe_id, ~tem_artefatos_finais())
    feedbacks = select(
        literal_column("'FEEDBACK'").label("tipo"),
        col(FeedbackMentoria.id).label("id"),
        col(FeedbackMentoria.criado_em).label("ocorrido_em"),
    ).where(FeedbackMentoria.equipe_id == equipe_id)
    linha_do_tempo = union_all(entregas, feedbacks).subquery("linha_do_tempo")
    consulta = (
        select(linha_do_tempo.c.tipo, linha_do_tempo.c.id)
        .order_by(linha_do_tempo.c.ocorrido_em.desc(), linha_do_tempo.c.id)
        .limit(limite)
        .offset(deslocamento)
    )
    return [(tipo, id_) for tipo, id_ in (await db.exec(consulta)).all()]


async def entregas_por_id(db: AsyncSession, ids: list[UUID]) -> dict[UUID, EntregaMentoria]:
    consulta = select(EntregaMentoria).where(col(EntregaMentoria.id).in_(ids))
    return {entrega.id: entrega for entrega in (await db.exec(consulta)).all()}


async def feedbacks_por_id(db: AsyncSession, ids: list[UUID]) -> dict[UUID, LinhaFeedback]:
    consulta = _com_autor_e_correcao().where(col(FeedbackMentoria.id).in_(ids))
    return {linha[0].id: linha for linha in (await db.exec(consulta)).all()}


async def ultimos_feedbacks(
    db: AsyncSession, equipe_ids: set[UUID]
) -> dict[UUID, FeedbackMentoria]:
    """O feedback mais recente de cada equipe, em uma consulta só (índice por equipe e data)."""
    consulta = (
        select(FeedbackMentoria)
        .where(col(FeedbackMentoria.equipe_id).in_(equipe_ids))
        .distinct(col(FeedbackMentoria.equipe_id))
        .order_by(
            col(FeedbackMentoria.equipe_id),
            col(FeedbackMentoria.criado_em).desc(),
            col(FeedbackMentoria.id),
        )
    )
    return {fb.equipe_id: fb for fb in (await db.exec(consulta)).all()}


async def recentes(
    db: AsyncSession, equipe_id: UUID, quantidade: int
) -> list[tuple[FeedbackMentoria, str | None]]:
    consulta = (
        select(FeedbackMentoria, Usuario.nome)
        .join(Usuario, col(Usuario.id) == col(FeedbackMentoria.autor_id))
        .where(FeedbackMentoria.equipe_id == equipe_id)
        .order_by(col(FeedbackMentoria.criado_em).desc(), FeedbackMentoria.id)
        .limit(quantidade)
    )
    return list((await db.exec(consulta)).all())


async def marco_tem_feedbacks(db: AsyncSession, marco_id: UUID) -> bool:
    return (await db.exec(select(exists().where(col(FeedbackMentoria.marco_id) == marco_id)))).one()


async def vigente_travada(db: AsyncSession, equipe_id: UUID) -> AtribuicaoMentor | None:
    """Atribuição vigente com trava compartilhada até o fim da transação: uma substituição
    simultânea espera o feedback terminar, e um feedback que chega depois dela já não a encontra."""
    consulta = (
        select(AtribuicaoMentor)
        .where(
            AtribuicaoMentor.equipe_id == equipe_id,
            col(AtribuicaoMentor.encerrada_em).is_(None),
        )
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    return (await db.exec(consulta)).first()
