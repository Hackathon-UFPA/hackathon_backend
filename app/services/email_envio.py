"""Envio dos e-mails da fila (RNF28).

`processar_lote` é o que o worker repete: reserva um lote, entrega cada e-mail pelo provedor e
registra o resultado. Cada passo confirma a própria transação, então nada fica preso e dois
workers (ou duas instâncias da API) não enviam o mesmo e-mail.

Erro temporário reagenda com espera crescente (base * 2^(tentativa-1), com teto). Erro permanente,
ou o fim das tentativas, leva o e-mail a FALHA. A garantia é "pelo menos uma vez": se o worker cair
depois de o provedor aceitar a mensagem e antes de registrar, ela pode sair de novo.
"""

import logging
from dataclasses import dataclass

from app.const.config import settings
from app.const.enums import StatusEmail
from app.controllers.email_outbox import (
    esgotar_reservas_vencidas,
    get_email,
    registrar_envio,
    registrar_falha,
    registrar_nova_tentativa,
    reservar_emails,
)
from app.db.db import async_session
from app.integrations.email import (
    ErroEnvioPermanente,
    ErroEnvioTemporario,
    MensagemEmail,
    ProvedorEmail,
    obter_provedor,
)

logger = logging.getLogger(__name__)


@dataclass
class ResumoLote:
    enviados: int = 0
    reagendados: int = 0
    falhas: int = 0

    @property
    def total(self) -> int:
        return self.enviados + self.reagendados + self.falhas


def espera_em_segundos(tentativa: int) -> int:
    """Espera antes da próxima tentativa, depois da `tentativa`-ésima (1, 2, 3...)."""
    return min(
        settings.EMAIL_BACKOFF_BASE_SEGUNDOS * 2 ** (tentativa - 1),
        settings.EMAIL_BACKOFF_MAX_SEGUNDOS,
    )


async def processar_lote(provedor: ProvedorEmail | None = None) -> ResumoLote:
    provedor = provedor or obter_provedor()
    async with async_session() as db:
        await esgotar_reservas_vencidas(db)
        lote = await reservar_emails(
            db, limite=settings.EMAIL_LOTE, reserva_segundos=settings.EMAIL_RESERVA_SEGUNDOS
        )
        await db.commit()

    resumo = ResumoLote()
    for email in lote:
        async with async_session() as db:
            if (email.get("chave_idempotencia") or "").startswith("convite-mentor:"):
                # A reserva já foi confirmada. Revalidar sob a mesma trava do cancelamento,
                # mantida até o resultado do provedor, impede usar uma cópia antiga do lote.
                atual = await get_email(db, email["id"], para_atualizar=True)
                if (
                    atual is None
                    or atual.cancelado_em is not None
                    or atual.status != StatusEmail.ENVIANDO
                    or atual.tentativas != email["tentativas"]
                ):
                    continue
            await _entregar(db, email, provedor, resumo)
            await db.commit()
    return resumo


async def _entregar(db, email: dict, provedor: ProvedorEmail, resumo: ResumoLote):
    mensagem = MensagemEmail(
        destinatario=email["destinatario_email"],
        destinatario_nome=email["destinatario_nome"],
        assunto=email["assunto"],
        texto=email["corpo_texto"],
        html=email["corpo_html"],
    )
    mensagem_id = None
    erro = None
    definitivo = False
    try:
        mensagem_id = await provedor.enviar(mensagem)
    except ErroEnvioPermanente as falha:
        erro, definitivo = str(falha), True
    except ErroEnvioTemporario as falha:
        erro = str(falha)
        definitivo = email["tentativas"] >= email["max_tentativas"]
    except Exception as falha:
        # Falha que o provedor não classificou: trata como temporária
        erro = f"{type(falha).__name__}: {falha}"[:500]
        definitivo = email["tentativas"] >= email["max_tentativas"]
        if not (email.get("chave_idempotencia") or "").startswith("convite-mentor:"):
            logger.exception("Erro inesperado ao enviar o e-mail %s", email["id"])

    if (email.get("chave_idempotencia") or "").startswith("convite-mentor:") and erro:
        # Nem um provedor inesperado pode persistir/logar o corpo secreto de um convite.
        erro = "Falha no envio do convite de mentor."
    if erro is None:
        await registrar_envio(db, email["id"], mensagem_id)
        resumo.enviados += 1
    elif definitivo:
        await registrar_falha(db, email["id"], erro)
        resumo.falhas += 1
        logger.error("E-mail %s não enviado: %s", email["id"], erro)
    else:
        await registrar_nova_tentativa(
            db, email["id"], erro, espera_em_segundos(email["tentativas"])
        )
        resumo.reagendados += 1
        logger.warning("E-mail %s falhou, nova tentativa agendada: %s", email["id"], erro)
