from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.painel_mentor import DetalheEquipeNoPainel, PainelMentorResponse
from app.security.dependencias import exigir_papeis
from app.services import painel_mentor as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(
    prefix="/me/mentoria/painel",
    tags=["Painel do mentor"],
    responses=respostas_de_erro(
        {
            401: "JWT ausente, inválido ou conta desativada.",
            403: "Mentor sem ativação concluída ou perfil sem permissão.",
        }
    ),
)

Db = Annotated[AsyncSession, Depends(get_session)]
Mentor = Annotated[Usuario, Depends(exigir_papeis(PapelUsuario.MENTOR))]


@router.get("", response_model=PainelMentorResponse)
async def painel(
    db: Db,
    mentor: Mentor,
    hackathon_id: UUID | None = None,
    equipe_id: UUID | None = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
):
    """RF41. Equipes atribuídas hoje ao mentor autenticado, com progresso e pendências.

    Entram só equipes homologadas, com proposta aprovada e da organização do mentor. O `resumo`
    soma todas as equipes filtradas. Ordem: edição, nome da equipe e id. DEV recebe apenas os
    vínculos da própria conta.
    """
    return await service.painel(db, mentor, hackathon_id, equipe_id, limite, deslocamento)


@router.get(
    "/equipes/{equipe_id}",
    response_model=DetalheEquipeNoPainel,
    responses=respostas_de_erro(
        {404: "Equipe inexistente ou fora do acompanhamento vigente do mentor."}
    ),
)
async def detalhar_equipe(equipe_id: UUID, db: Db, mentor: Mentor):
    """RF41. Integrantes (nome e função), calendário e entregas de uma equipe acompanhada.

    Não traz e-mails, notas, pareceres nem conversas.
    """
    return await service.detalhar_equipe(db, mentor, equipe_id)
