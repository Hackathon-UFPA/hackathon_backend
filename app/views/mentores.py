from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.controllers.mentor import listar_mentores
from app.db.db import get_session
from app.models import Usuario
from app.schemas.mentor import (
    ConviteMentorAdminResponse,
    ConviteMentorCreate,
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
    {404: "Mentor ou edição não encontrados", 409: "Conflito de cadastro, RN33 ou capacidade"}
)


@router.post("", response_model=MentorResponse, status_code=201, responses=ERROS_MENTOR)
async def cadastrar(dados: MentorCreate, db: AsyncSession = Depends(get_session)):
    """Cadastra mentor inativo e emite convite vinculado a hackathon_id (RF37, RN24, RN33).

    Falhas de e-mail preservam o cadastro; consulte /{id}/convites para verificar pendências.
    """
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
    """Edita o cadastro; alterar e-mail exige nova ativação pelo destinatário.

    Reduzir max_equipes abaixo dos vínculos vigentes, em qualquer edição, retorna 409.
    """
    return await service.editar(db, mentor_id, dados)


@router.post("/{mentor_id}/convite", response_model=MentorResponse, responses=ERROS_MENTOR)
async def reenviar_convite(
    mentor_id: UUID, dados: ConviteMentorCreate, db: AsyncSession = Depends(get_session)
):
    """Emite convite para a edição informada, inclusive para mentor já ativo.

    Revoga convites e cancela mensagens não enviadas somente da mesma edição.
    Confira falhas de enfileiramento/entrega em GET /{id}/convites. Não retorna tokens.
    """
    return await service.reenviar_convite(db, mentor_id, dados.hackathon_id)


@router.get(
    "/{mentor_id}/convites",
    response_model=list[ConviteMentorAdminResponse],
    responses=ERROS_MENTOR,
)
async def listar_convites(
    mentor_id: UUID,
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    """Histórico paginado e pendências de convite, sem hashes, tokens ou corpos de e-mail."""
    return await service.listar_convites(db, mentor_id, limite, deslocamento)


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
    responses=respostas_de_erro(
        {
            400: "Convite inválido ou expirado",
            409: "Edição diferente da vinculada ao convite",
        }
    ),
)
async def consultar_convite(dados: ConviteMentorRequest, db: AsyncSession = Depends(get_session)):
    """Consulta perfil e termos para onboarding. O token vem no corpo para evitar logs de URL."""
    mentor, convite = await service.validar_convite(db, dados.token, dados.hackathon_id)
    termos = await termos_vigentes_do_hackathon(db, convite.hackathon_id)
    return ConviteMentorResponse(
        mentor=mentor,
        termos=termos,
        senha_necessaria=mentor.senha_hash is None,
        hackathon_id=convite.hackathon_id,
    )


@router_publico.post(
    "/ativacao",
    response_model=MentorResponse,
    responses=respostas_de_erro(
        {
            400: "Convite inválido, expirado ou utilizado",
            404: "Edição inexistente",
            409: "Edição incompatível com o convite, termos desatualizados ou não publicados",
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
