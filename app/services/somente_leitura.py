"""Modo somente leitura das equipes não aprovadas (RF34).

Depois que o resultado do hackathon é homologado, a equipe cuja proposta tem
`resultados_proposta.aprovada = false` só pode consultar. Toda rota de escrita ligada à
equipe chama `exigir_equipe_editavel` (inclusive para DEV: a regra é de estado, não de perfil).
Hackathon sem homologação, equipe aprovada e equipe sem proposta enviada não são afetados.

Corrida aceita: uma escrita que passou nesta checagem antes do commit da homologação vale.
"""

from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.controllers.resultado import equipe_reprovada
from app.exceptions.resultado import equipe_somente_leitura_apos_resultado


async def exigir_equipe_editavel(db: AsyncSession, equipe_id: UUID) -> None:
    if await equipe_reprovada(db, equipe_id):
        equipe_somente_leitura_apos_resultado()
