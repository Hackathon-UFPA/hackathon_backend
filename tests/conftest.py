import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.const.config import settings
from app.main import app
from app.security.senha import gerar_hash

SENHA_PADRAO = "segredo123"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def executar_sql(comando: str, **params):
    """Roda um comando no banco e confirma a transação. Os testes de API gravam de verdade
    (a API confirma as próprias transações), então quem usa isto precisa limpar depois."""

    async def main():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                resultado = await conn.execute(text(comando), params)
                return resultado.mappings().all() if resultado.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(main())


@pytest.fixture
def sql():
    return executar_sql


@pytest.fixture
def hackathon_aberto():
    """Hackathon com inscrições abertas. A data de início distante faz dele o escolhido no
    cadastro, mesmo que o banco de desenvolvimento já tenha outros em inscrições."""
    id_ = executar_sql(
        "INSERT INTO hackathon (nome, status, data_inicio)"
        " VALUES ('Teste de autenticação', 'INSCRICOES', '2099-01-01') RETURNING id"
    )[0]["id"]
    yield id_
    executar_sql("DELETE FROM comprovantes_vinculo WHERE hackathon_id = :id", id=id_)
    executar_sql("DELETE FROM hackathon WHERE id = :id", id=id_)


@pytest.fixture
def emails_criados():
    """E-mails usados no teste. Ao final, apaga os usuários (e comprovantes) deles."""
    emails: list[str] = []
    yield emails
    if emails:
        minusculos = [email.lower() for email in emails]
        executar_sql(
            "DELETE FROM comprovantes_vinculo WHERE usuario_id IN"
            " (SELECT id FROM usuarios WHERE lower(email) = ANY(:emails))",
            emails=minusculos,
        )
        executar_sql("DELETE FROM usuarios WHERE lower(email) = ANY(:emails)", emails=minusculos)


@pytest.fixture
def novo_email(emails_criados):
    def gerar() -> str:
        email = f"auth_{uuid4().hex[:12]}@testes.com"
        emails_criados.append(email)
        return email

    return gerar


@pytest.fixture
def usuario_no_banco(novo_email):
    """Cria um usuário direto no banco, sem passar pelo cadastro da API."""

    def criar(
        *,
        papel: str = "PARTICIPANTE",
        senha: str | None = SENHA_PADRAO,
        ativo: bool = True,
        situacao_conta: str = "ATIVA",
    ) -> dict:
        email = novo_email()
        id_ = executar_sql(
            "INSERT INTO usuarios (email, papel, senha_hash, ativo, situacao_conta)"
            " VALUES (:email, CAST(:papel AS papel_usuario), :senha_hash, :ativo,"
            " CAST(:situacao_conta AS situacao_conta)) RETURNING id",
            email=email,
            papel=papel,
            senha_hash=gerar_hash(senha) if senha else None,
            ativo=ativo,
            situacao_conta=situacao_conta,
        )[0]["id"]
        return {"id": id_, "email": email, "senha": senha}

    return criar
