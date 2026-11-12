"""Worker da fila de e-mails (RNF28): envia o que está pendente e repete a cada intervalo."""

import asyncio
import logging
from contextlib import suppress

from app.const.config import settings
from app.services.email_envio import processar_lote

logger = logging.getLogger(__name__)


async def worker_de_email(parar: asyncio.Event) -> None:
    """Roda até `parar` ser acionado. Um erro num lote vai para o log e não derruba o worker.
    Se o lote veio cheio, busca o próximo na hora, sem esperar o intervalo."""
    logger.info("Worker de e-mail iniciado (intervalo de %ss)", settings.EMAIL_INTERVALO_SEGUNDOS)
    while not parar.is_set():
        lote_cheio = False
        try:
            resumo = await processar_lote()
            lote_cheio = resumo.total >= settings.EMAIL_LOTE
        except Exception:
            logger.exception("Falha ao processar a fila de e-mail")
        if lote_cheio:
            continue
        with suppress(TimeoutError):
            await asyncio.wait_for(parar.wait(), timeout=settings.EMAIL_INTERVALO_SEGUNDOS)
    logger.info("Worker de e-mail encerrado")
