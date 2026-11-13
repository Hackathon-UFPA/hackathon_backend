from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.tema import TemaCreate, TemaResponse, TemaUpdate
from app.security.dependencias import exigir_papeis, usuario_opcional
from app.security.permissoes import PERFIS_QUE_GERENCIAM_TEMAS_E_RUBRICAS
from app.services import tema as service
from app.utils.openapi import respostas_de_erro

router_hackathon = APIRouter(prefix="/hackathons/{hackathon_id}/temas", tags=["Temas"])
router = APIRouter(prefix="/temas", tags=["Temas"])

gerencia_temas = exigir_papeis(*PERFIS_QUE_GERENCIAM_TEMAS_E_RUBRICAS)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ERRO_409_TITULO = "Já existe um tema com este título neste hackathon"


@router_hackathon.post(
    "",
    response_model=TemaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar tema",
    description=(
        "Comitê Científico, Organizador (exceção administrativa) ou DEV (RF15). O tema tem "
        "título, descrição e pelo menos um ODS (1 a 17); `contexto` é opcional. O título é "
        "único na edição."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado", 409: ERRO_409_TITULO}
    ),
)
async def cadastrar_tema(
    hackathon_id: UUID,
    dados: TemaCreate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_temas),
):
    return await service.criar(db, hackathon_id, dados)


@router_hackathon.get(
    "",
    response_model=list[TemaResponse],
    summary="Catálogo de temas da edição (público)",
    description=(
        "**Não exige login** (RF10, RF17): retorna os temas **ativos**, que são os que podem "
        "ser escolhidos na proposta (RF15). `incluir_inativos=true` mostra também os "
        "desativados e exige token de Comitê Científico, Organizador ou DEV: sem token, 401; "
        "outros perfis, 403. Se o token for enviado, ele precisa ser válido (401 se não for)."
    ),
    responses=respostas_de_erro(
        {
            401: "Token inválido, ou `incluir_inativos` sem token",
            403: ERRO_403,
            404: "Hackathon não encontrado",
        }
    ),
)
async def listar_temas(
    hackathon_id: UUID,
    incluir_inativos: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    usuario: Usuario | None = Depends(usuario_opcional),
):
    return await service.listar(db, usuario, hackathon_id, incluir_inativos)


@router.get(
    "/{tema_id}",
    response_model=TemaResponse,
    summary="Consultar tema (público)",
    description=(
        "**Não exige login.** Tema desativado só é visível para Comitê Científico, Organizador "
        "ou DEV; para os demais, retorna 404. Se o token for enviado, ele precisa ser válido."
    ),
    responses=respostas_de_erro({401: "Token inválido", 404: "Tema não encontrado"}),
)
async def obter_tema(
    tema_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario | None = Depends(usuario_opcional),
):
    return await service.consultar(db, usuario, tema_id)


@router.patch(
    "/{tema_id}",
    response_model=TemaResponse,
    summary="Editar, ativar ou desativar tema",
    description=(
        "Comitê Científico, Organizador (exceção administrativa) ou DEV (RF15). Altera apenas "
        "os campos enviados; `ativo=false` desativa o tema, que deixa de aparecer para escolha "
        "nas propostas. Rascunhos que já usam o tema não podem ser enviados enquanto ele "
        "estiver desativado. Título, descrição, ODS e ativo não aceitam null."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Tema não encontrado", 409: ERRO_409_TITULO}
    ),
)
async def editar_tema(
    tema_id: UUID,
    dados: TemaUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_temas),
):
    return await service.editar(db, tema_id, dados)


@router.delete(
    "/{tema_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Excluir tema",
    description=(
        "Comitê Científico, Organizador (exceção administrativa) ou DEV. Não é possível "
        "excluir um tema que já tem propostas ligadas a ele, inclusive rascunhos (RN04): "
        "nesse caso, desative-o."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Tema não encontrado",
            409: "O tema tem propostas ligadas a ele",
        }
    ),
)
async def excluir_tema(
    tema_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_temas),
):
    await service.excluir(db, tema_id)
