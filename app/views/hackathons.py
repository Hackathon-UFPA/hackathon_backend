from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.hackathon import HackathonCreate, HackathonResponse, HackathonUpdate
from app.security.dependencias import exigir_papeis
from app.security.permissoes import PERFIS_QUE_GERENCIAM_EDITAL
from app.services import hackathon as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/admin/hackathons", tags=["Hackathons"])

gerencia_edital = exigir_papeis(*PERFIS_QUE_GERENCIAM_EDITAL)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ERRO_422_DATAS = "Campos inválidos, períodos fora de ordem ou min_integrantes > max_integrantes"


@router.post(
    "",
    response_model=HackathonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar hackathon",
    description=(
        "Somente Organizador ou DEV. Cria uma edição do hackathon. Todos os campos são "
        "opcionais; `status` começa em `INSCRICOES` e a equipe tem de 3 a 5 integrantes por "
        "padrão. As datas são gravadas em UTC; cada período precisa terminar depois de começar, "
        "e `homologacao_fim` não pode ser antes de `inscricoes_fim`."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 422: ERRO_422_DATAS}),
)
async def cadastrar_hackathon(
    dados: HackathonCreate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_edital),
):
    return await service.criar(db, dados)


@router.patch(
    "/{hackathon_id}",
    response_model=HackathonResponse,
    summary="Editar hackathon",
    description=(
        "Somente Organizador ou DEV. Altera apenas os campos enviados; as regras de datas e de "
        "tamanho da equipe valem para o resultado final. `status`, `min_integrantes` e "
        "`max_integrantes` não aceitam null. Para encerrar uma edição que já tem dados, use "
        "`status = CANCELADO` em vez de excluí-la."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado", 422: ERRO_422_DATAS}
    ),
)
async def editar_hackathon(
    hackathon_id: UUID,
    dados: HackathonUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_edital),
):
    return await service.editar(db, hackathon_id, dados)


@router.delete(
    "/{hackathon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Excluir hackathon",
    description=(
        "Somente Organizador ou DEV. Só exclui uma edição sem nada ligado a ela (equipes, "
        "temas, termos, rubrica, comprovantes...). Caso contrário responde 409: altere o "
        "status para `CANCELADO`."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: "O hackathon tem dados ligados a ele",
        }
    ),
)
async def excluir_hackathon(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_edital),
):
    await service.excluir(db, hackathon_id)
