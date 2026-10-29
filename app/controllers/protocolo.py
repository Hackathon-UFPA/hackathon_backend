from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Protocolo


async def criar_protocolo(db: AsyncSession, protocolo: Protocolo) -> Protocolo:
    """Sem commit. O número é gerado pelo banco, então o `refresh` o traz de volta."""
    db.add(protocolo)
    await db.flush()
    await db.refresh(protocolo)
    return protocolo
