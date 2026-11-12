import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.const.config import settings
from app.db.db import async_engine
from app.jobs.email import worker_de_email

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan é uma função executada no início e no fim de um processo do fastapi. O que está
    antes do yield é executado no início, o que está depois é executado ao finalizar o processo.
    Aqui sobe o worker da fila de e-mails (EMAIL_WORKER_ATIVO) e o encerra ao final."""

    parar = asyncio.Event()
    worker = None
    if settings.EMAIL_WORKER_ATIVO:
        worker = asyncio.create_task(worker_de_email(parar), name="worker-email")

    yield

    parar.set()
    if worker is not None:
        try:
            await asyncio.wait_for(worker, timeout=settings.SMTP_TIMEOUT_SEGUNDOS + 5)
        except TimeoutError:
            logger.warning("O worker de e-mail não encerrou a tempo e foi cancelado")

    await async_engine.dispose()
