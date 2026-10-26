from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.db.db import get_session
from app.schemas.auth import CadastroRequest, LoginRequest, TokenResponse
from app.schemas.usuario import UsuarioResponse
from app.services.auth import autenticar, cadastrar_participante

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/cadastro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def cadastrar(dados: CadastroRequest, db: AsyncSession = Depends(get_session)):
    return await cadastrar_participante(db, dados)


@router.post("/login", response_model=TokenResponse)
async def login(dados: LoginRequest, db: AsyncSession = Depends(get_session)):
    token = await autenticar(db, dados.email, dados.senha)
    return TokenResponse(access_token=token, expires_in=settings.JWT_EXPIRE_MINUTES * 60)
