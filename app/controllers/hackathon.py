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
