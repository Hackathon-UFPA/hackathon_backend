from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.auth import UsuarioAdminCreate
from app.schemas.usuario import UsuarioResponse
from app.security.dependencias import exigir_papeis
from app.services.usuario import cadastrar_usuario_por_perfil

router = APIRouter(prefix="/admin/usuarios", tags=["Usuários"])


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def cadastrar_usuario(
    dados: UsuarioAdminCreate,
    db: AsyncSession = Depends(get_session),
    quem_cadastra: Usuario = Depends(
        exigir_papeis(PapelUsuario.ORGANIZADOR, PapelUsuario.COMITE_CIENTIFICO)
    ),
):
    return await cadastrar_usuario_por_perfil(db, quem_cadastra, dados)
