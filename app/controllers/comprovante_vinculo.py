from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ComprovanteVinculo


async def criar_comprovante(
    db: AsyncSession, comprovante: ComprovanteVinculo
) -> ComprovanteVinculo:
    """Só adiciona à sessão; quem chama decide quando confirmar a transação."""
    db.add(comprovante)
    await db.flush()
    return comprovante
