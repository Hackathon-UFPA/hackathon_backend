import logging

from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health(db: AsyncSession = Depends(get_session)):
    try:
        await db.exec(select(1))
        banco = "ok"
    except Exception as error:
        logger.error("Banco de dados indisponível: %s", error)
        banco = "indisponivel"

    return {"status": "ok", "database": banco}
