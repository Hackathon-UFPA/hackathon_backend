from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon
from app.models import Hackathon


async def get_hackathon_com_inscricoes(db: AsyncSession) -> Hackathon | None:
    """Hackathon com inscrições abertas; se houver mais de um, o de início mais recente."""
    consulta = (
        select(Hackathon)
        .where(Hackathon.status == StatusHackathon.INSCRICOES)
        .order_by(Hackathon.data_inicio.desc().nulls_last())
        .limit(1)
    )
    return (await db.exec(consulta)).first()
