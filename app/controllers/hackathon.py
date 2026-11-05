from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon
from app.models import Hackathon
from app.validations.inscricao import inscricoes_abertas


async def get_hackathon_com_inscricoes(db: AsyncSession) -> Hackathon | None:
    """Hackathon com inscrições abertas; se houver mais de um, o de início mais recente."""
    consulta = (
        select(Hackathon)
        .where(Hackathon.status == StatusHackathon.INSCRICOES)
        .order_by(Hackathon.data_inicio.desc().nulls_last())
    )
    hackathons = (await db.exec(consulta)).all()
    return next((hackathon for hackathon in hackathons if inscricoes_abertas(hackathon)), None)


async def get_hackathon_para_atualizar(db: AsyncSession, hackathon_id: UUID) -> Hackathon | None:
    """Trava a linha até o fim da transação: serializa distribuições simultâneas."""
    consulta = select(Hackathon).where(Hackathon.id == hackathon_id).with_for_update()
    return (await db.exec(consulta)).first()


async def salvar_hackathon(db: AsyncSession, hackathon: Hackathon) -> Hackathon:
    db.add(hackathon)
    await db.flush()
    return hackathon


async def excluir_hackathon(db: AsyncSession, hackathon: Hackathon) -> None:
    await db.delete(hackathon)
    await db.flush()


async def listar_hackathons(db: AsyncSession) -> list[Hackathon]:
    """Mais recentes primeiro; edição sem data de início vai para o fim."""
    consulta = select(Hackathon).order_by(Hackathon.data_inicio.desc().nulls_last(), Hackathon.nome)
    return list((await db.exec(consulta)).all())
