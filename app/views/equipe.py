from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.equipe import EquipeCreate, EquipeResponse, EquipeUpdate
from app.security.dependencias import usuario_ativo
from app.services.equipe import consultar, criar, editar, listar_minhas
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/equipes", tags=["Equipes"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"


@router.post(
    "",
    response_model=EquipeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar equipe",
    description=(
        "Cria a equipe em `EM_FORMACAO` e o vínculo `LIDER` do usuário autenticado na mesma "
        "transação (RF18). Exige hackathon existente com `status = INSCRICOES` (RN06) e "
        "nenhum vínculo do usuário nesta edição (RN02). Não exige mínimo de integrantes ou "
        "aceites de termos nesta operação. Aceites têm endpoints próprios. "
        "Aceita somente `hackathon_id` e `nome` opcional; o líder é definido pelo sistema."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: "Inscrições fechadas ou usuário já participa de equipe nesta edição",
        }
    ),
)
async def criar_uma_equipe(
    dados: EquipeCreate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await criar(db, usuario, dados)


# A rota fixa precisa ser registrada antes de /{equipe_id}.
@router.get(
    "/minhas",
    response_model=list[EquipeResponse],
    summary="Minhas equipes",
    description=(
        "Lista apenas as equipes das quais o usuário autenticado é integrante, em todas as "
        "edições, inclusive para DEV. Não inclui dados de usuários ou convites."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403}),
)
async def minhas_equipes(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_ativo)
):
    return await listar_minhas(db, usuario)


@router.get(
    "/{equipe_id}",
    response_model=EquipeResponse,
    summary="Consultar equipe",
    description="Consulta restrita a integrantes da equipe, com a exceção técnica DEV.",
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Equipe não encontrada"}),
)
async def consultar_equipe(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await consultar(db, usuario, equipe_id)


@router.patch(
    "/{equipe_id}",
    response_model=EquipeResponse,
    summary="Editar nome da equipe",
    description=(
        "O líder técnico pode editar apenas `nome` (RF24, RN03), com a exceção técnica DEV. "
        "Exige equipe em `EM_FORMACAO` e hackathon com `status = INSCRICOES` (RN06). "
        "Campos adicionais, como situação, datas e hackathon, são rejeitados."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Equipe não encontrada",
            409: "Inscrições fechadas ou equipe fora de EM_FORMACAO",
        }
    ),
)
async def editar_equipe(
    equipe_id: UUID,
    dados: EquipeUpdate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await editar(db, usuario, equipe_id, dados)
