"""Resolução da edição nos fluxos individuais, sem escolher entre edições simultâneas."""

from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.controllers.hackathon import get_hackathon_com_inscricoes
from app.exceptions.auth import inscricoes_indisponiveis
from app.exceptions.convite import fora_do_periodo_de_inscricao
from app.models import Hackathon, Usuario
from app.services.hackathon import obter_acessivel
from app.validations.inscricao import inscricoes_abertas


async def resolver_edicao(
    db: AsyncSession,
    hackathon_id: UUID | None,
    *,
    exigir_inscricoes: bool = True,
    usuario: Usuario | None = None,
) -> Hackathon:
    """ID explícito nunca faz fallback. Consultas históricas não exigem inscrições abertas;
    rascunhos continuam privados. Sem ID, mantém o legado apenas sem ambiguidade."""
    if hackathon_id is None:
        hackathon = await get_hackathon_com_inscricoes(db)
        if hackathon is None:
            inscricoes_indisponiveis()
    else:
        # Mesma privacidade de GET /hackathons/{id}, antes de revelar status ou prazo.
        hackathon = await obter_acessivel(db, hackathon_id, usuario)
        if exigir_inscricoes and not inscricoes_abertas(hackathon):
            fora_do_periodo_de_inscricao()
    return hackathon
