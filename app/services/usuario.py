import asyncio

from sqlmodel.ext.asyncio.session import AsyncSession

from app.controllers.usuario import criar_usuario
from app.exceptions.auth import acesso_negado
from app.models import Usuario
from app.schemas.auth import UsuarioAdminCreate
from app.security.permissoes import pode_cadastrar
from app.security.senha import gerar_hash


async def cadastrar_usuario_por_perfil(
    db: AsyncSession, quem_cadastra: Usuario, dados: UsuarioAdminCreate
) -> Usuario:
    """Cria um usuário de qualquer perfil que `quem_cadastra` tenha direito de cadastrar (RF07,
    RF08). A conta já nasce ativa: o comprovante de vínculo vale só para o cadastro público."""
    if not pode_cadastrar(quem_cadastra.papel, dados.papel):
        acesso_negado()

    usuario = await criar_usuario(
        db,
        Usuario(
            **dados.model_dump(exclude={"senha", "email"}),
            email=dados.email.lower(),
            senha_hash=await asyncio.to_thread(gerar_hash, dados.senha),
        ),
    )
    await db.commit()
    return usuario
