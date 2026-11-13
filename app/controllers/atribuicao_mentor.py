from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AtribuicaoMentor,
    Equipe,
    EventoNotificacaoMentoria,
    ResultadoProposta,
    Usuario,
)


async def equipe_aprovada(db: AsyncSession, equipe_id: UUID, hackathon_id: UUID) -> bool:
    return (
        await db.exec(
            select(ResultadoProposta.id).where(
                ResultadoProposta.equipe_id == equipe_id,
                ResultadoProposta.hackathon_id == hackathon_id,
                col(ResultadoProposta.aprovada).is_(True),
            )
        )
    ).first() is not None


async def vigente(db: AsyncSession, equipe_id: UUID) -> AtribuicaoMentor | None:
    return (
        await db.exec(
            select(AtribuicaoMentor).where(
                AtribuicaoMentor.equipe_id == equipe_id,
                col(AtribuicaoMentor.encerrada_em).is_(None),
            )
        )
    ).first()


async def bloquear_mentores(db: AsyncSession, ids: set[UUID]) -> None:
    # A ordem global evita deadlock ao trocar dois mentores entre equipes diferentes.
    await db.exec(
        select(Usuario).where(col(Usuario.id).in_(ids)).order_by(Usuario.id).with_for_update()
    )


async def contar_vigentes(db: AsyncSession, mentor_id: UUID) -> int:
    return (
        await db.exec(
            select(func.count())
            .select_from(AtribuicaoMentor)
            .where(
                AtribuicaoMentor.mentor_id == mentor_id,
                col(AtribuicaoMentor.encerrada_em).is_(None),
            )
        )
    ).one()


async def historico(db: AsyncSession, equipe_id: UUID, limite: int, deslocamento: int):
    return list(
        (
            await db.exec(
                select(AtribuicaoMentor)
                .where(AtribuicaoMentor.equipe_id == equipe_id)
                .order_by(col(AtribuicaoMentor.atribuido_em).desc(), col(AtribuicaoMentor.id))
                .limit(limite)
                .offset(deslocamento)
            )
        ).all()
    )


async def salvar(db: AsyncSession, atribuicao: AtribuicaoMentor) -> None:
    db.add(atribuicao)
    await db.flush()


async def equipes_do_mentor(
    db: AsyncSession,
    mentor_id: UUID,
    hackathon_id: UUID | None,
    apenas_vigentes: bool,
    limite: int,
    deslocamento: int,
):
    consulta = (
        select(AtribuicaoMentor, Equipe.nome)
        .join(Equipe)
        .where(AtribuicaoMentor.mentor_id == mentor_id)
    )
    if apenas_vigentes:
        consulta = consulta.where(col(AtribuicaoMentor.encerrada_em).is_(None))
    if hackathon_id is not None:
        consulta = consulta.where(AtribuicaoMentor.hackathon_id == hackathon_id)
    return (
        await db.exec(
            consulta.order_by(col(AtribuicaoMentor.atribuido_em).desc(), AtribuicaoMentor.id)
            .limit(limite)
            .offset(deslocamento)
        )
    ).all()


async def eventos_pendentes_plataforma(db: AsyncSession, limite: int = 100):
    """Adaptador da futura central: consumir e publicar na mesma transação, por id do evento."""
    return list(
        (
            await db.exec(
                select(EventoNotificacaoMentoria)
                .where(col(EventoNotificacaoMentoria.publicado_na_plataforma_em).is_(None))
                .order_by(EventoNotificacaoMentoria.criado_em, EventoNotificacaoMentoria.id)
                .limit(limite)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
