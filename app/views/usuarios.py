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

router = APIRouter(prefix="/admin/usuarios", tags=["Usuários"])

gestor_de_usuarios = exigir_papeis(PapelUsuario.ORGANIZADOR, PapelUsuario.COMITE_CIENTIFICO)


@router.get("/perfis", response_model=PerfisCadastraveisResponse)
async def listar_perfis_cadastraveis(quem_cadastra: Usuario = Depends(gestor_de_usuarios)):
    return PerfisCadastraveisResponse(perfis=perfis_cadastraveis(quem_cadastra.papel))


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def cadastrar_usuario(
    dados: UsuarioAdminCreate,
    db: AsyncSession = Depends(get_session),
    quem_cadastra: Usuario = Depends(gestor_de_usuarios),
):
    return await cadastrar_usuario_por_perfil(db, quem_cadastra, dados)
