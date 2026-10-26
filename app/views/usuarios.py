from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.auth import PerfisCadastraveisResponse, UsuarioAdminCreate
from app.schemas.usuario import UsuarioResponse
from app.security.dependencias import exigir_papeis
from app.security.permissoes import perfis_cadastraveis
from app.services.usuario import cadastrar_usuario_por_perfil
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/admin/usuarios", tags=["Usuários"])

gestor_de_usuarios = exigir_papeis(PapelUsuario.ORGANIZADOR, PapelUsuario.COMITE_CIENTIFICO)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"


@router.get(
    "/perfis",
    response_model=PerfisCadastraveisResponse,
    summary="Perfis que posso cadastrar",
    description=(
        "Lista os perfis que o usuário logado pode criar (RF07, RF08), para a interface montar "
        "o formulário de cadastro sem repetir a hierarquia: o Organizador cadastra qualquer "
        "perfil de negócio e o Comitê Científico cadastra Comitê Técnico e Mentor."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: "Perfil sem permissão para esta rota, ou conta ainda pendente"}
    ),
)
async def listar_perfis_cadastraveis(quem_cadastra: Usuario = Depends(gestor_de_usuarios)):
    return PerfisCadastraveisResponse(perfis=perfis_cadastraveis(quem_cadastra.papel))


@router.post(
    "",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar usuário de outro perfil",
    description=(
        "Cria um usuário com a conta já **ativa** (RF07, RF08). Quem cadastra escolhe o `papel`, "
        "dentro da lista de `GET /admin/usuarios/perfis`, e define a senha inicial. Não pede "
        "comprovante de vínculo: isso vale só para o cadastro público de participante."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: "Perfil sem permissão para esta rota, conta pendente, ou `papel` que quem "
            "cadastra não pode criar",
            409: "E-mail já cadastrado",
        }
    ),
)
async def cadastrar_usuario(
    dados: UsuarioAdminCreate,
    db: AsyncSession = Depends(get_session),
    quem_cadastra: Usuario = Depends(gestor_de_usuarios),
):
    return await cadastrar_usuario_por_perfil(db, quem_cadastra, dados)
