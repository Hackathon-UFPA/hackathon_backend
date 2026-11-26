from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.hackathon import HackathonCreate, HackathonResponse, HackathonUpdate
from app.security.dependencias import exigir_papeis, usuario_opcional
from app.security.organizacao import gestor_do_hackathon
from app.security.permissoes import PERFIS_QUE_GERENCIAM_EDITAL
from app.services import hackathon as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/admin/hackathons", tags=["Hackathons"])
router_publico = APIRouter(prefix="/hackathons", tags=["Hackathons"])

gerencia_edital = exigir_papeis(*PERFIS_QUE_GERENCIAM_EDITAL)
gerencia_o_hackathon = gestor_do_hackathon(*PERFIS_QUE_GERENCIAM_EDITAL)
ERRO_403_ORG = "Conta pendente, perfil sem permissão, ou hackathon de outra organização"

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ERRO_422_DATAS = "Campos inválidos, períodos fora de ordem ou min_integrantes > max_integrantes"


@router.post(
    "",
    response_model=HackathonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar hackathon",
    description=(
        "Somente Organizador ou DEV. Cria uma edição do hackathon da organização de quem "
        "cadastra. Todos os campos são "
        "opcionais; `status` começa em `INSCRICOES` e a equipe tem de 3 a 5 integrantes por "
        "padrão. As datas são gravadas em UTC; cada período precisa terminar depois de começar, "
        "e `homologacao_fim` não pode ser antes de `inscricoes_fim`."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 422: ERRO_422_DATAS}),
)
async def cadastrar_hackathon(
    dados: HackathonCreate,
    db: AsyncSession = Depends(get_session),
    criador: Usuario = Depends(gerencia_edital),
):
    return await service.criar(db, dados, criador)


@router.patch(
    "/{hackathon_id}",
    response_model=HackathonResponse,
    summary="Editar hackathon",
    description=(
        "Somente Organizador da organização dona ou DEV. Altera apenas os campos enviados; "
        "as regras de datas e de "
        "tamanho da equipe valem para o resultado final. `status`, `min_integrantes` e "
        "`max_integrantes` não aceitam null. Para encerrar uma edição que já tem dados, use "
        "`status = CANCELADO` em vez de excluí-la. Alterar `avaliadores_por_projeto_final` "
        "exige uma edição aberta antes e depois da operação."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403_ORG,
            404: "Hackathon não encontrado",
            409: "Alteração da configuração técnica em edição finalizada ou cancelada",
            422: ERRO_422_DATAS,
        }
    ),
)
async def editar_hackathon(
    hackathon_id: UUID,
    dados: HackathonUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_o_hackathon),
):
    return await service.editar(db, hackathon_id, dados)


@router.delete(
    "/{hackathon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Excluir hackathon",
    description=(
        "Somente Organizador da organização dona ou DEV. Só exclui uma edição sem nada "
        "ligado a ela (equipes, "
        "temas, termos, rubrica, comprovantes...). Caso contrário responde 409: altere o "
        "status para `CANCELADO`."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403_ORG,
            404: "Hackathon não encontrado",
            409: "O hackathon tem dados ligados a ele",
        }
    ),
)
async def excluir_hackathon(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_o_hackathon),
):
    await service.excluir(db, hackathon_id)


@router.get(
    "",
    response_model=list[HackathonResponse],
    summary="Hackathons da minha organização",
    description=(
        "Organizador (e DEV). Todas as edições da organização de quem pede, inclusive os "
        "rascunhos, das mais recentes para as mais antigas. DEV vê as de todas as organizações."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403}),
)
async def listar_hackathons_da_organizacao(
    db: AsyncSession = Depends(get_session),
    gestor: Usuario = Depends(gerencia_edital),
):
    return await service.listar_da_organizacao(db, gestor)


@router_publico.get(
    "",
    response_model=list[HackathonResponse],
    summary="Listar hackathons",
    description=(
        "Público, sem login. Vitrine com as edições de todas as organizações (ou só de uma, "
        "com `organizacao_id`), das mais recentes (`data_inicio`) para as mais antigas. "
        "Rascunhos ficam de fora."
    ),
)
async def listar_hackathons(
    organizacao_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
):
    return await service.listar_publicos(db, organizacao_id)


@router_publico.get(
    "/{hackathon_id}",
    response_model=HackathonResponse,
    summary="Consultar hackathon",
    description=(
        "Público, sem login. Dados e prazos de uma edição. Rascunho só aparece para a equipe "
        "interna da organização dona (com token); para os demais responde 404."
    ),
    responses=respostas_de_erro({404: "Hackathon não encontrado"}),
)
async def obter_hackathon(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario | None = Depends(usuario_opcional),
):
    return await service.consultar(db, hackathon_id, usuario)
