from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoProtocolo
from app.models import Protocolo


async def criar_protocolo(db: AsyncSession, protocolo: Protocolo) -> Protocolo:
    """Sem commit. O número é gerado pelo banco, então o `refresh` o traz de volta."""
    db.add(protocolo)
    await db.flush()
    await db.refresh(protocolo)
    return protocolo


async def get_protocolo_da_proposta(db: AsyncSession, equipe_id: UUID) -> Protocolo | None:
    """Protocolo do envio mais recente (BE-S5-09: cada versão da proposta tem o seu)."""
    consulta = (
        select(Protocolo)
        .where(Protocolo.equipe_id == equipe_id, Protocolo.tipo == TipoProtocolo.PROPOSTA)
        .order_by(col(Protocolo.emitido_em).desc(), col(Protocolo.numero).desc())
    )
    return (await db.exec(consulta)).first()
