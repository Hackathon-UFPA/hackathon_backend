from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.controllers.mentor import listar_mentores
from app.db.db import get_session
from app.models import Usuario
from app.schemas.mentor import (
    ConviteMentorRequest,
    ConviteMentorResponse,
    MentorAtivacao,
    MentorCreate,
    MentorReativacao,
    MentorResponse,
    MentorUpdate,
)
from app.security.dependencias import exigir_papeis
from app.services import mentor as service
from app.services.termo import termos_vigentes_do_hackathon
from app.utils.openapi import respostas_de_erro

gestor = exigir_papeis(PapelUsuario.COMITE_CIENTIFICO, PapelUsuario.ORGANIZADOR)
router = APIRouter(
    prefix="/admin/mentores",
    tags=["Mentores"],
    dependencies=[Depends(gestor)],
    responses=respostas_de_erro({401: "Não autenticado", 403: "Perfil não autorizado"}),
)
router_publico = APIRouter(prefix="/mentores", tags=["Mentores"])
ERROS_MENTOR = respostas_de_erro(
    {404: "Mentor não encontrado", 409: "Conflito de cadastro ou RN33"}
)


@router.post("", response_model=MentorResponse, status_code=201, responses=ERROS_MENTOR)
async def cadastrar(dados: MentorCreate, db: AsyncSession = Depends(get_session)):
    """Cadastra mentor inativo e enfileira convite de uso único (RF37, RN24, RN33)."""
    return await service.cadastrar(db, dados)


@router.get("", response_model=list[MentorResponse])
async def listar(
    ativo: bool | None = None,
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    return await listar_mentores(db, ativo, limite, deslocamento)


@router.get("/{mentor_id}", response_model=MentorResponse, responses=ERROS_MENTOR)
async def consultar(mentor_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.consultar(db, mentor_id)


@router.patch("/{mentor_id}", response_model=MentorResponse, responses=ERROS_MENTOR)
async def editar(mentor_id: UUID, dados: MentorUpdate, db: AsyncSession = Depends(get_session)):
    """Edita o cadastro; alterar e-mail exige nova ativação pelo destinatário."""
    return await service.editar(db, mentor_id, dados)


@router.post("/{mentor_id}/convite", response_model=MentorResponse, responses=ERROS_MENTOR)
async def reenviar_convite(mentor_id: UUID, db: AsyncSession = Depends(get_session)):
    """Gera novo convite e invalida links anteriores; não expõe token na resposta."""
    return await service.reenviar_convite(db, mentor_id)


@router.post("/{mentor_id}/ativar", response_model=MentorResponse, responses=ERROS_MENTOR)
async def reativar(
    mentor_id: UUID, dados: MentorReativacao, db: AsyncSession = Depends(get_session)
):
    """Reativa somente quem já concluiu a RN33 e aceitou os termos vigentes da edição."""
    return await service.reativar(db, mentor_id, dados.hackathon_id)


@router.post("/{mentor_id}/desativar", response_model=MentorResponse, responses=ERROS_MENTOR)
async def desativar(mentor_id: UUID, db: AsyncSession = Depends(get_session)):
    """Preserva histórico, bloqueia acesso e novas atribuições; invalida convites abertos."""
    return await service.desativar(db, mentor_id)


@router_publico.post(
    "/convite/consultar",
    response_model=ConviteMentorResponse,
    responses=respostas_de_erro({400: "Convite inválido ou expirado", 404: "Edição inexistente"}),
)
async def consultar_convite(dados: ConviteMentorRequest, db: AsyncSession = Depends(get_session)):
    """Consulta perfil e termos para onboarding. O token vem no corpo para evitar logs de URL."""
    mentor, _ = await service.validar_convite(db, dados.token)
    termos = await termos_vigentes_do_hackathon(db, dados.hackathon_id)
    return ConviteMentorResponse(
        mentor=mentor, termos=termos, senha_necessaria=mentor.senha_hash is None
    )


@router_publico.post(
    "/ativacao",
    response_model=MentorResponse,
    responses=respostas_de_erro(
        {
            400: "Convite inválido, expirado ou utilizado",
            404: "Edição inexistente",
            409: "Termos desatualizados ou não publicados",
            422: "Perfil, senha ou aceites incompletos",
        }
    ),
)
async def ativar(dados: MentorAtivacao, db: AsyncSession = Depends(get_session)) -> Usuario:
    """O destinatário completa o perfil, define senha se necessário e aceita ambos os termos.

    Somente o commit desta operação consome o convite e ativa o mentor (RN33).
    Não exige comprovante de vínculo acadêmico ou profissional.
    """
    return await service.ativar_por_convite(db, dados)
