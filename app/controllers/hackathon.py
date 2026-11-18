from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon
from app.exceptions.hackathon import selecao_de_hackathon_ambigua
from app.models import Hackathon, Organizacao
from app.validations.inscricao import inscricoes_abertas


async def get_hackathon_com_inscricoes(db: AsyncSession) -> Hackathon | None:
    """Compatibilidade legada: só resolve automaticamente uma única edição elegível."""
    consulta = select(Hackathon).where(Hackathon.status == StatusHackathon.INSCRICOES)
    hackathons = (await db.exec(consulta)).all()
    elegiveis = [hackathon for hackathon in hackathons if inscricoes_abertas(hackathon)]
    if len(elegiveis) > 1:
        selecao_de_hackathon_ambigua()
    return elegiveis[0] if elegiveis else None


async def get_hackathon_para_atualizar(db: AsyncSession, hackathon_id: UUID) -> Hackathon | None:
    """Trava a linha até o fim da transação: serializa distribuições simultâneas."""
    consulta = select(Hackathon).where(Hackathon.id == hackathon_id).with_for_update()
    return (await db.exec(consulta)).first()


async def get_hackathon_compartilhado(db: AsyncSession, hackathon_id: UUID) -> Hackathon | None:
    """FOR SHARE: vários envios de proposta andam juntos, mas esperam (e são esperados por)
    quem trava a edição com FOR UPDATE, como a distribuição e a homologação do resultado."""
    consulta = select(Hackathon).where(Hackathon.id == hackathon_id).with_for_update(read=True)
    return (await db.exec(consulta)).first()


async def salvar_hackathon(db: AsyncSession, hackathon: Hackathon) -> Hackathon:
    db.add(hackathon)
    await db.flush()
    return hackathon


async def excluir_hackathon(db: AsyncSession, hackathon: Hackathon) -> None:
    await db.delete(hackathon)
    await db.flush()


async def listar_hackathons(
    db: AsyncSession,
    *,
    publicos: bool = False,
    filtrar_organizacao: bool = False,
    organizacao_id: UUID | None = None,
) -> list[tuple[Hackathon, str | None]]:
    """Mais recentes primeiro; edição sem data de início vai para o fim. Cada item vem com o
    nome da organização dona. `publicos` deixa de fora os rascunhos."""
    consulta = (
        select(Hackathon, Organizacao.nome)
        .join(Organizacao, Organizacao.id == Hackathon.organizacao_id, isouter=True)
        .order_by(Hackathon.data_inicio.desc().nulls_last(), Hackathon.nome)
    )
    if publicos:
        consulta = consulta.where(Hackathon.status != StatusHackathon.RASCUNHO)
    if filtrar_organizacao:
        consulta = consulta.where(Hackathon.organizacao_id.is_not_distinct_from(organizacao_id))
    return [(hackathon, nome) for hackathon, nome in (await db.exec(consulta)).all()]


async def get_nome_da_organizacao(db: AsyncSession, organizacao_id: UUID | None) -> str | None:
    if organizacao_id is None:
        return None
    organizacao = await db.get(Organizacao, organizacao_id)
    return organizacao.nome if organizacao else None
