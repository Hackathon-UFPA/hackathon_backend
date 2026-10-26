from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.db.db import get_session
from app.models import Usuario
from app.schemas.auth import CadastroRequest, LoginRequest, TokenResponse
from app.schemas.usuario import UsuarioResponse
from app.security.dependencias import usuario_atual
from app.security.token import criar_token
from app.services.auth import autenticar, cadastrar_participante

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/cadastro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def cadastrar(dados: CadastroRequest, db: AsyncSession = Depends(get_session)):
    return await cadastrar_participante(db, dados)


@router.post("/login", response_model=TokenResponse)
async def login(dados: LoginRequest, db: AsyncSession = Depends(get_session)):
    usuario = await autenticar(db, dados.email, dados.senha)
    return TokenResponse(
        access_token=criar_token(usuario.id),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        usuario=usuario,
    )


@router.get("/me", response_model=UsuarioResponse)
async def meus_dados(usuario: Usuario = Depends(usuario_atual)):
    """Dados de quem está logado. Conta pendente também pode consultar."""
    return usuario
