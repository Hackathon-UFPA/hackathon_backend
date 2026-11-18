"""Resolução da edição nos fluxos individuais, sem escolher entre edições simultâneas."""

from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon
from app.controllers.equipe import get_hackathon_by_id
from app.controllers.hackathon import get_hackathon_com_inscricoes
from app.exceptions.auth import inscricoes_indisponiveis
from app.exceptions.convite import fora_do_periodo_de_inscricao, hackathon_nao_encontrado
from app.models import Hackathon
from app.validations.inscricao import inscricoes_abertas


async def resolver_edicao(
    db: AsyncSession, hackathon_id: UUID | None, *, exigir_inscricoes: bool = True
) -> Hackathon:
    """ID explícito nunca faz fallback. Consultas históricas não exigem inscrições abertas;
    rascunhos continuam privados. Sem ID, mantém o legado apenas sem ambiguidade."""
    if hackathon_id is None:
        hackathon = await get_hackathon_com_inscricoes(db)
        if hackathon is None:
            inscricoes_indisponiveis()
    else:
        hackathon = await get_hackathon_by_id(db, hackathon_id)
        if hackathon is None:
            hackathon_nao_encontrado()
        if exigir_inscricoes:
            if not inscricoes_abertas(hackathon):
                fora_do_periodo_de_inscricao()
        elif hackathon.status == StatusHackathon.RASCUNHO:
            hackathon_nao_encontrado()
    return hackathon
