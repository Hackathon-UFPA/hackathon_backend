"""Cria um usuário direto no banco, sem passar pela API.

Serve para o primeiro Organizador: como só quem tem permissão cadastra os demais perfis,
alguém precisa existir antes. Uso (dentro do container da API):

    python -m app.scripts.criar_usuario --email org@ufpa.br --nome "Fulano" --papel ORGANIZADOR
"""

import argparse
import asyncio
import getpass
import sys

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.controllers.usuario import criar_usuario
from app.db.db import async_engine, async_session
from app.models import Usuario
from app.security.senha import gerar_hash, validar_forca_da_senha


async def cadastrar(db: AsyncSession, email: str, nome: str, papel: PapelUsuario, senha: str):
    """Cria o usuário com a conta ativa. Levanta ValueError se a senha for fraca e
    HTTPException se o e-mail já existir."""
    usuario = await criar_usuario(
        db,
        Usuario(
            email=email.lower(),
            nome=nome,
            papel=papel,
            senha_hash=gerar_hash(validar_forca_da_senha(senha)),
        ),
    )
    await db.commit()
    return usuario


def pedir_senha() -> str:
    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Confirme a senha: "):
        sys.exit("As senhas não conferem.")
    return senha


async def main() -> None:
    parser = argparse.ArgumentParser(description="Cria um usuário direto no banco.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--nome", required=True)
    parser.add_argument(
        "--papel", choices=[p.value for p in PapelUsuario], default=PapelUsuario.ORGANIZADOR.value
    )
    argumentos = parser.parse_args()

    # A senha é pedida no terminal para não ficar no histórico de comandos
    senha = pedir_senha()
    try:
        async with async_session() as db:
            usuario = await cadastrar(
                db, argumentos.email, argumentos.nome, PapelUsuario(argumentos.papel), senha
            )
    except ValueError as erro:
        sys.exit(str(erro))
    except HTTPException as erro:
        sys.exit(erro.detail)
    finally:
        await async_engine.dispose()

    print(f"Usuário criado: {usuario.email} ({usuario.papel})")


if __name__ == "__main__":
    asyncio.run(main())
