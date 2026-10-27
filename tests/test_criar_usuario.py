"""Script de apoio que cria o primeiro Organizador (app/scripts/criar_usuario.py)."""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import PapelUsuario
from app.scripts.criar_usuario import cadastrar
from app.security.senha import senha_confere

SENHA = "segredo123"


def rodar_cadastro(email: str, senha: str = SENHA, papel=PapelUsuario.ORGANIZADOR):
    """Usa um engine próprio: o da API fica preso ao loop de eventos do TestClient."""

    async def main():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                return await cadastrar(db, email, "Fulano de Tal", papel, senha)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def test_cria_usuario_ativo_que_consegue_entrar(client, novo_email):
    email = novo_email()

    usuario = rodar_cadastro(email)

    assert usuario.papel == PapelUsuario.ORGANIZADOR
    assert usuario.situacao_conta == "ATIVA"
    assert senha_confere(SENHA, usuario.senha_hash)
    resposta = client.post("/auth/login", json={"email": email, "senha": SENHA})
    assert resposta.status_code == 200


def test_guarda_o_email_em_minusculas(novo_email):
    email = novo_email()

    assert rodar_cadastro(email.upper()).email == email.lower()


def test_recusa_senha_fraca(novo_email):
    with pytest.raises(ValueError, match="pelo menos"):
        rodar_cadastro(novo_email(), senha="fraca")


def test_recusa_email_ja_cadastrado(novo_email):
    email = novo_email()
    rodar_cadastro(email)

    with pytest.raises(HTTPException) as erro:
        rodar_cadastro(email)

    assert erro.value.status_code == 409
