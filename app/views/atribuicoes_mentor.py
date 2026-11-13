from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.atribuicao_mentor import (
    AtribuicaoCreate,
    AtribuicaoEncerrar,
    AtribuicaoResponse,
    AtribuicaoSubstituir,
    EquipeAcompanhadaResponse,
    MentorDaEquipeResponse,
    TreinamentoResponse,
)
from app.security.dependencias import exigir_papeis, usuario_ativo
from app.services import atribuicao_mentor as service
from app.utils.openapi import respostas_de_erro

gestor = exigir_papeis(PapelUsuario.COMITE_CIENTIFICO, PapelUsuario.ORGANIZADOR)
router = APIRouter(
    tags=["Atribuições de mentores"],
    responses=respostas_de_erro(
        {
            401: "Sem autenticação ou conta desativada",
            403: "Conta pendente ou perfil sem permissão",
            404: "Equipe, mentor, edição ou atribuição inexistentes",
            409: "Treinamento pendente, equipe/mentor inelegível, capacidade ou vínculo alterado",
        }
    ),
)
ADMIN_EQUIPE = "/admin/equipes/{equipe_id}/mentoria"


@router.post(ADMIN_EQUIPE, response_model=AtribuicaoResponse, status_code=201)
async def atribuir(
    equipe_id: UUID,
    dados: AtribuicaoCreate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(gestor),
):
    """RF38/RN16/RN24/RN33: atribui mentor elegível após treinamento à equipe aprovada.

    Comitê Científico, Organizador (exceção administrativa) e DEV. Capacidade global entre
    edições, uma atribuição vigente por equipe. Avisos por e-mail entram no outbox; eventos
    in-app permanecem pendentes para a central. Nenhuma regra de negócio é dispensada por perfil.
    """
    return await service.atribuir(db, usuario, equipe_id, dados)


@router.put(ADMIN_EQUIPE, response_model=AtribuicaoResponse)
async def substituir(
    equipe_id: UUID,
    dados: AtribuicaoSubstituir,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(gestor),
):
    """Substitui o vínculo esperado; preserva quem/quando/motivo e notifica envolvidos.

    `atribuicao_atual_id` protege contra alterações concorrentes (409 se já mudou).
    O novo mentor deve cumprir as mesmas regras da primeira atribuição.
    """
    return await service.atribuir(
        db, usuario, equipe_id, dados, atribuicao_atual_id=dados.atribuicao_atual_id
    )


@router.post(ADMIN_EQUIPE + "/encerrar", response_model=AtribuicaoResponse)
async def encerrar(
    equipe_id: UUID,
    dados: AtribuicaoEncerrar,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(gestor),
):
    """Encerra logicamente o vínculo esperado e libera capacidade; não apaga o histórico."""
    return await service.encerrar(db, usuario, equipe_id, dados)


@router.get(ADMIN_EQUIPE, response_model=AtribuicaoResponse)
async def consultar_admin(
    equipe_id: UUID, db: AsyncSession = Depends(get_session), _: Usuario = Depends(gestor)
):
    return await service.consultar_admin(db, equipe_id)


@router.get(ADMIN_EQUIPE + "/historico", response_model=list[AtribuicaoResponse])
async def historico(
    equipe_id: UUID,
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gestor),
):
    return await service.historico(db, equipe_id, limite, deslocamento)


@router.get("/admin/mentores/{mentor_id}/equipes", response_model=list[EquipeAcompanhadaResponse])
async def equipes_do_mentor(
    mentor_id: UUID,
    hackathon_id: UUID | None = None,
    apenas_vigentes: bool = True,
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gestor),
):
    return await service.equipes_do_mentor(
        db, mentor_id, hackathon_id, apenas_vigentes, limite, deslocamento
    )


@router.get("/me/mentoria/equipes", response_model=list[EquipeAcompanhadaResponse])
async def minhas_equipes(
    hackathon_id: UUID | None = None,
    apenas_vigentes: bool = True,
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(exigir_papeis(PapelUsuario.MENTOR)),
):
    """Somente equipes do mentor autenticado; não recebe id de outro mentor."""
    return await service.equipes_do_mentor(
        db, usuario.id, hackathon_id, apenas_vigentes, limite, deslocamento
    )


@router.get("/equipes/{equipe_id}/mentor", response_model=MentorDaEquipeResponse)
async def mentor_da_equipe(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    """Integrantes da própria equipe (e DEV) consultam contato e situação do mentor.

    Não revela capacidade, outras equipes, senha, aceites ou motivos administrativos.
    Vínculo encerrado não é retornado. Mentor desativado é identificado por `ativo=false`.
    """
    return await service.mentor_da_equipe(db, usuario, equipe_id)


@router.get("/admin/hackathons/{hackathon_id}/treinamento", response_model=TreinamentoResponse)
async def treinamento(
    hackathon_id: UUID, db: AsyncSession = Depends(get_session), _: Usuario = Depends(gestor)
):
    return await service.treinamento(db, hackathon_id)


@router.post(
    "/admin/hackathons/{hackathon_id}/treinamento/concluir", response_model=TreinamentoResponse
)
async def concluir_treinamento(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(exigir_papeis(PapelUsuario.ORGANIZADOR)),
):
    """Organizador/DEV confirma o término real do treinamento após homologação do resultado.

    Marco auditado e idempotente por edição; não inferido do status ATIVO ou de uma data local.
    Comitê Científico consulta o marco, mas não o conclui nesta política administrativa.
    """
    return await service.concluir_treinamento(db, usuario, hackathon_id)
