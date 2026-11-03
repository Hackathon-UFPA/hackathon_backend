import logging

from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "",
    summary="Verificar saúde da API",
    description=(
        "Rota pública, sem login. Responde 200 com `status` e `database` (`ok` ou "
        "`indisponivel`), mesmo que o banco esteja fora do ar."
    ),
    responses={
        200: {
            "content": {
                "application/json": {"example": {"status": "ok", "database": "ok"}},
            }
        }
    },
)
async def health(db: AsyncSession = Depends(get_session)):
    try:
        await db.exec(select(1))
        banco = "ok"
    except Exception as error:
        logger.error("Banco de dados indisponível: %s", error)
        banco = "indisponivel"

    return {"status": "ok", "database": banco}
