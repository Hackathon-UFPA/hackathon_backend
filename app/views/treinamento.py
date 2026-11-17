from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.conteudo import (
    MaterialCreate,
    MaterialResponse,
    SessaoCreate,
    SessaoResponse,
    SessaoUpdate,
)
from app.security.dependencias import usuario_ativo
from app.security.organizacao import gestor_do_hackathon
from app.security.permissoes import PERFIS_QUE_GERENCIAM_EDITAL
from app.services import treinamento as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(
    prefix="/admin/hackathons/{hackathon_id}/treinamento", tags=["Treinamento (admin)"]
)
router_consulta = APIRouter(prefix="/hackathons/{hackathon_id}/treinamento", tags=["Treinamento"])

# Só o Organizador da organização dona do hackathon (e DEV)
gerencia_treinamento = gestor_do_hackathon(*PERFIS_QUE_GERENCIAM_EDITAL)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão (só Organizador e DEV)"
ERROS = {401: ERRO_401, 403: ERRO_403, 404: "Hackathon, sessão ou material não encontrado"}


@router.post(
    "/sessoes",
    response_model=SessaoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar sessão do treinamento",
    description=(
        "Somente Organizador ou DEV (RF35). Cada sessão tem `titulo`, `inicio` (UTC; data sem "
        "fuso vale como UTC), `fim` opcional e **local ou link** (`local`, `link_url` em `https`, "
        "RNF20). Nasce **não publicada**: as equipes só veem depois de `publicado = true`. O aviso "
        "às equipes quando algo muda depende da Q09 e ainda não existe."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Campo inválido, fim antes do início ou sem local"}),
)
async def criar_sessao(
    hackathon_id: UUID,
    dados: SessaoCreate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_treinamento),
):
    return await service.criar_sessao(db, hackathon_id, dados)


@router.get(
    "/sessoes",
    response_model=list[SessaoResponse],
    summary="Listar sessões do treinamento (administração)",
    description=(
        "Somente Organizador ou DEV. Publicadas ou não, com os materiais, em ordem "
        "cronológica. Filtro `publicado`; paginação por `limite` (1 a 100) e `deslocamento`."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Parâmetro inválido"}),
)
async def listar_sessoes(
    hackathon_id: UUID,
    publicado: bool | None = None,
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_treinamento),
):
    return await service.listar_sessoes_admin(
        db, hackathon_id, publicado=publicado, limite=limite, deslocamento=deslocamento
    )


@router.patch(
    "/sessoes/{sessao_id}",
    response_model=SessaoResponse,
    summary="Editar sessão do treinamento",
    description=(
        "Somente Organizador ou DEV. Altera só o que foi enviado; `descricao`, `fim`, `local` e "
        "`link_url` aceitam `null`, mas a sessão precisa manter local ou link e o `fim` não "
        "pode ser antes do `inicio`."
    ),
    responses=respostas_de_erro(
        {**ERROS, 422: "Campo inválido, período fora de ordem ou sem local"}
    ),
)
async def editar_sessao(
    hackathon_id: UUID,
    sessao_id: UUID,
    dados: SessaoUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_treinamento),
):
    return await service.editar_sessao(db, hackathon_id, sessao_id, dados)


@router.delete(
    "/sessoes/{sessao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Excluir sessão do treinamento",
    description="Somente Organizador ou DEV. Os materiais da sessão saem junto.",
    responses=respostas_de_erro(ERROS),
)
async def excluir_sessao(
    hackathon_id: UUID,
    sessao_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_treinamento),
):
    await service.excluir_sessao(db, hackathon_id, sessao_id)


@router.post(
    "/sessoes/{sessao_id}/materiais",
    response_model=MaterialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Anexar material à sessão",
    description=(
        "Somente Organizador ou DEV (RF35). O material é um **link** `https` (RNF20): a API não "
        "recebe arquivos. Vai para o fim da lista da sessão."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Título ou link inválido"}),
)
async def adicionar_material(
    hackathon_id: UUID,
    sessao_id: UUID,
    dados: MaterialCreate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_treinamento),
):
    return await service.adicionar_material(db, hackathon_id, sessao_id, dados)


@router.delete(
    "/sessoes/{sessao_id}/materiais/{material_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remover material da sessão",
    description="Somente Organizador ou DEV.",
    responses=respostas_de_erro(ERROS),
)
async def remover_material(
    hackathon_id: UUID,
    sessao_id: UUID,
    material_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_treinamento),
):
    await service.remover_material(db, hackathon_id, sessao_id, material_id)


@router_consulta.get(
    "",
    response_model=list[SessaoResponse],
    summary="Agenda e materiais do treinamento",
    description=(
        "Exige conta ativa (RF35). Devolve as sessões **publicadas**, com os materiais, em "
        "ordem cronológica. Só integrantes de **equipe aprovada** na edição, o Organizador, o "
        "Comitê Científico e o DEV podem ver; qualquer outra pessoa recebe 403, sem revelar o "
        "conteúdo. Quem organiza vê rascunhos pela rota de administração."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: "Conta pendente, ou quem pede não é de equipe aprovada nem da organização",
            404: "Hackathon não encontrado",
        }
    ),
)
async def treinamento(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await service.treinamento_da_edicao(db, usuario, hackathon_id)
