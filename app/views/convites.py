from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.convite import (
    ConviteAceite,
    ConviteEnvio,
    ConviteRecebidoResponse,
    ConviteResponse,
)
from app.security.dependencias import usuario_ativo
from app.services.convite import (
    aceitar_convite,
    cancelar_convite,
    enviar_convite,
    listar_convites,
    listar_convites_recebidos,
    recusar_convite,
)
from app.utils.openapi import respostas_de_erro

router = APIRouter(tags=["Convites"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"


@router.post(
    "/equipes/{equipe_id}/convites",
    response_model=ConviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Convidar integrante",
    description=(
        "O **líder técnico** da equipe convida uma pessoa por nome e e-mail (RF18). O convite "
        "nasce `PENDENTE` e aparece no painel de quem tiver conta com aquele e-mail. O total de "
        "integrantes mais convites pendentes não passa do máximo do hackathon. Só vale durante "
        "as inscrições (RN06). O envio do e-mail ainda não está implementado."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Equipe não encontrada",
            409: "Inscrições fechadas, equipe sem vagas, pessoa já integrante, ou convite "
            "pendente/aceito para o mesmo e-mail",
        }
    ),
)
async def convidar(
    equipe_id: UUID,
    dados: ConviteEnvio,
    db: AsyncSession = Depends(get_session),
    lider: Usuario = Depends(usuario_ativo),
):
    return await enviar_convite(db, lider, equipe_id, dados)


@router.get(
    "/equipes/{equipe_id}/convites",
    response_model=list[ConviteResponse],
    summary="Convites da equipe",
    description=(
        "Todos os convites da equipe, com o estado de cada um (`PENDENTE`, `ACEITO`, `RECUSADO` "
        "ou `CANCELADO`). É por aqui que o líder vê quem recusou. Só integrantes da equipe."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Equipe não encontrada"}),
)
async def listar_da_equipe(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await listar_convites(db, usuario, equipe_id)


@router.get(
    "/convites/meus",
    response_model=list[ConviteRecebidoResponse],
    summary="Convites que recebi",
    description=(
        "Convites `PENDENTE` dirigidos ao e-mail de quem está logado (RF19), para o painel. "
        "O e-mail é comparado sem diferenciar maiúsculas."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403}),
)
async def meus_convites(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_ativo)
):
    return await listar_convites_recebidos(db, usuario)


@router.post(
    "/convites/{convite_id}/aceitar",
    response_model=ConviteResponse,
    summary="Aceitar convite",
    description=(
        "Quem recebeu o convite entra na equipe (RF19) e aceita o regulamento e o termo de "
        "consentimento (RF20). Envie em `termos_ids` os ids das versões **vigentes** que a "
        "pessoa leu (`GET /hackathons/{id}/termos/vigentes`); a data, a hora e a versão ficam "
        "registradas. Só quem ainda não está em outra equipe do hackathon (RN02) e só durante "
        "as inscrições (RN06)."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Convite não existe, ou não é dirigido a quem está logado",
            409: "Convite já respondido, inscrições fechadas, já está em outra equipe, equipe "
            "sem vagas, termos não publicados ou desatualizados",
            422: "Faltou aceitar o regulamento ou o termo de consentimento vigente",
        }
    ),
)
async def aceitar(
    convite_id: UUID,
    dados: ConviteAceite,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await aceitar_convite(db, usuario, convite_id, dados.termos_ids)


@router.post(
    "/convites/{convite_id}/recusar",
    response_model=ConviteResponse,
    summary="Recusar convite",
    description=(
        "Quem recebeu recusa o convite (RF19). A vaga volta a ficar livre e o líder vê o "
        "convite como `RECUSADO` em `GET /equipes/{id}/convites`."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Convite não existe, ou não é dirigido a quem está logado",
            409: "Convite já respondido, ou inscrições fechadas",
        }
    ),
)
async def recusar(
    convite_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await recusar_convite(db, usuario, convite_id)


@router.post(
    "/convites/{convite_id}/cancelar",
    response_model=ConviteResponse,
    summary="Cancelar convite",
    description="O líder técnico retira um convite ainda `PENDENTE`; a vaga volta a ficar livre.",
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Convite não encontrado",
            409: "Convite já respondido ou cancelado",
        }
    ),
)
async def cancelar(
    convite_id: UUID,
    db: AsyncSession = Depends(get_session),
    lider: Usuario = Depends(usuario_ativo),
):
    return await cancelar_convite(db, lider, convite_id)
