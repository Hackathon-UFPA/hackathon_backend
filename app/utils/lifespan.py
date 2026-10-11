import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.db import async_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan é uma função executada no início e no fim de um processo do fastapi. O que está
    antes do yield é executado no início, o que está depois é executado ao finalizar o processo.
    Ex.: iniciar jobs agendados (app/jobs) antes do yield e cancelá-los depois."""

    yield

    await async_engine.dispose()
