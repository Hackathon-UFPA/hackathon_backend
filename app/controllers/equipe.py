from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import SituacaoEquipe
from app.models import Equipe, Hackathon, MembroEquipe
from app.schemas.equipe import EquipeUpdate
from app.utils.generic_db_operations import atualizar_instancia


async def get_equipe_by_id(
    db: AsyncSession, equipe_id: UUID, *, para_atualizar: bool = False
) -> Equipe | None:
    """Com `para_atualizar`, trava a linha até o fim da transação: serve para contar vagas sem
    que dois aceites simultâneos estourem o limite da equipe."""
    consulta = select(Equipe).where(Equipe.id == equipe_id)
    if para_atualizar:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def get_equipe_por_chave(db: AsyncSession, criador_id: UUID, chave: str) -> Equipe | None:
    """A equipe que este usuário criou com esta Idempotency-Key, se houver (BE-S5-02)."""
    consulta = select(Equipe).where(
        Equipe.criada_por == criador_id, Equipe.chave_idempotencia == chave
    )
    return (await db.exec(consulta)).first()


async def get_hackathon_id_da_equipe(db: AsyncSession, equipe_id: UUID) -> UUID | None:
    """Só o id da edição, sem carregar a equipe: quem trava a edição antes da equipe não deixa
    um objeto Equipe antigo no identity map da sessão."""
    consulta = select(Equipe.hackathon_id).where(Equipe.id == equipe_id)
    return (await db.exec(consulta)).first()


async def get_hackathon_by_id(db: AsyncSession, hackathon_id: UUID) -> Hackathon | None:
    return await db.get(Hackathon, hackathon_id)


async def criar_equipe(db: AsyncSession, equipe: Equipe) -> Equipe:
    """Persiste a equipe sem commit; o service confirma junto com o vínculo do líder."""
    db.add(equipe)
    await db.flush()
    return equipe


async def listar_equipes_do_usuario(db: AsyncSession, usuario_id: UUID) -> list[Equipe]:
    consulta = (
        select(Equipe)
        .join(MembroEquipe, col(MembroEquipe.equipe_id) == col(Equipe.id))
        .where(MembroEquipe.usuario_id == usuario_id)
        .order_by(col(Equipe.criado_em).desc().nulls_last(), col(Equipe.id))
    )
    return list((await db.exec(consulta)).all())


async def atualizar_equipe(db: AsyncSession, equipe: Equipe, dados: EquipeUpdate) -> Equipe:
    await atualizar_instancia(equipe, dados)
    db.add(equipe)
    await db.flush()
    return equipe


async def listar_equipes_para_homologacao(db: AsyncSession, hackathon_id: UUID) -> list[Equipe]:
    """Equipes com a inscrição concluída (aguardando ou já homologadas), travadas para
    atualização na ordem do id, o que evita deadlock entre reavaliações simultâneas."""
    consulta = (
        select(Equipe)
        .where(
            Equipe.hackathon_id == hackathon_id,
            col(Equipe.situacao).in_(
                [SituacaoEquipe.AGUARDANDO_HOMOLOGACAO, SituacaoEquipe.HOMOLOGADA]
            ),
        )
        .order_by(col(Equipe.id))
        .with_for_update()
    )
    return list((await db.exec(consulta)).all())


async def listar_homologadas_com_tamanho(
    db: AsyncSession, hackathon_id: UUID
) -> list[tuple[Equipe, int]]:
    """Equipes homologadas da edição com a quantidade de integrantes, pela ordem de homologação."""
    integrantes = (
        select(MembroEquipe.equipe_id, func.count().label("total"))
        .group_by(MembroEquipe.equipe_id)
        .subquery()
    )
    consulta = (
        select(Equipe, func.coalesce(integrantes.c.total, 0))
        .join(integrantes, integrantes.c.equipe_id == Equipe.id, isouter=True)
        .where(Equipe.hackathon_id == hackathon_id, Equipe.situacao == SituacaoEquipe.HOMOLOGADA)
        .order_by(col(Equipe.homologada_em).nulls_last(), Equipe.nome)
    )
    return [(equipe, total) for equipe, total in (await db.exec(consulta)).all()]


async def contar_por_situacao(db: AsyncSession, hackathon_id: UUID) -> dict[SituacaoEquipe, int]:
    consulta = (
        select(Equipe.situacao, func.count())
        .where(Equipe.hackathon_id == hackathon_id)
        .group_by(Equipe.situacao)
    )
    return {situacao: total for situacao, total in (await db.exec(consulta)).all()}
