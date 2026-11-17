from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.organizacao import OrganizacaoResponse, OrganizacaoUpdate
from app.security.dependencias import exigir_papeis, usuario_ativo
from app.services import organizacao as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/organizacoes", tags=["Organizações"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"


@router.get(
    "/minha",
    response_model=OrganizacaoResponse,
    summary="Minha organização",
    description="Equipe interna (Organizador, Comitês, Mentor). Dados da organização da conta.",
    responses=respostas_de_erro(
        {401: ERRO_401, 403: "Conta sem organização (Participante ou DEV)"}
    ),
)
async def minha_organizacao(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_ativo)
):
    return await service.da_equipe(db, usuario)


@router.patch(
    "/minha",
    response_model=OrganizacaoResponse,
    summary="Editar minha organização",
    description="Somente Organizador. Altera apenas os campos enviados.",
    responses=respostas_de_erro(
        {401: ERRO_401, 403: "Perfil sem permissão ou conta sem organização"}
    ),
)
async def editar_minha_organizacao(
    dados: OrganizacaoUpdate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(exigir_papeis(PapelUsuario.ORGANIZADOR)),
):
    return await service.editar(db, usuario, dados)


@router.get(
    "/{organizacao_id}",
    response_model=OrganizacaoResponse,
    summary="Consultar organização",
    description="Público, sem login. Página da organização na vitrine.",
    responses=respostas_de_erro({404: "Organização não encontrada"}),
)
async def obter_organizacao(organizacao_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.consultar(db, organizacao_id)
