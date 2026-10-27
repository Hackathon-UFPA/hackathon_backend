from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.exceptions.auth import email_ja_cadastrado
from app.exceptions.db import erro_de_integridade_sql
from app.models import Usuario


async def get_usuario_by_email(db: AsyncSession, email: str) -> Usuario | None:
    """Busca sem diferenciar maiúsculas, como o índice único do banco."""
    consulta = select(Usuario).where(func.lower(Usuario.email) == email.lower())
    return (await db.exec(consulta)).first()


async def criar_usuario(db: AsyncSession, usuario: Usuario) -> Usuario:
    """Só adiciona à sessão; quem chama decide quando confirmar a transação."""
    db.add(usuario)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        mensagem = str(error.orig)
        # Índices únicos do e-mail: o do banco original e o que ignora maiúsculas
        if "uq_usuarios_email_lower" in mensagem or "usuarios_email_key" in mensagem:
            email_ja_cadastrado()
        erro_de_integridade_sql(error)
    return usuario


async def registrar_falha_de_login(
    db: AsyncSession, usuario_id: UUID, max_tentativas: int, bloqueio: timedelta
) -> None:
    """Soma a falha no próprio UPDATE, sem ler antes, para que tentativas simultâneas não se
    percam. Ao chegar no limite, bloqueia a conta pelo tempo informado e zera o contador."""
    proxima = Usuario.tentativas_login + 1
    atingiu_limite = proxima >= max_tentativas
    await db.exec(
        update(Usuario)
        .where(Usuario.id == usuario_id)
        .values(
            tentativas_login=case((atingiu_limite, 0), else_=proxima),
            bloqueado_ate=case(
                (atingiu_limite, datetime.now(UTC) + bloqueio), else_=Usuario.bloqueado_ate
            ),
        )
    )


def zerar_falhas_de_login(db: AsyncSession, usuario: Usuario) -> None:
    usuario.tentativas_login = 0
    usuario.bloqueado_ate = None
    db.add(usuario)
