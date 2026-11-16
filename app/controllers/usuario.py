from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
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


async def get_usuario(
    db: AsyncSession, usuario_id: UUID, *, bloquear: bool = False
) -> Usuario | None:
    """Com `bloquear`, trava a linha: edição, desativação e troca de senha do mesmo usuário se
    enfileiram."""
    consulta = select(Usuario).where(Usuario.id == usuario_id)
    if bloquear:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def listar_usuarios(
    db: AsyncSession,
    papeis: list[PapelUsuario],
    *,
    papel: PapelUsuario | None,
    ativo: bool | None,
    busca: str | None,
    limite: int,
    deslocamento: int,
) -> list[Usuario]:
    consulta = select(Usuario).where(col(Usuario.papel).in_(papeis))
    if papel is not None:
        consulta = consulta.where(Usuario.papel == papel)
    if ativo is not None:
        consulta = consulta.where(Usuario.ativo == ativo)
    if busca:
        padrao = f"%{busca.lower()}%"
        consulta = consulta.where(
            or_(func.lower(Usuario.email).like(padrao), func.lower(Usuario.nome).like(padrao))
        )
    consulta = consulta.order_by(Usuario.email, Usuario.id).limit(limite).offset(deslocamento)
    return list((await db.exec(consulta)).all())


# Chave do bloqueio que serializa as mudanças capazes de tirar um Organizador do ar
BLOQUEIO_GESTAO_DE_ORGANIZADORES = 7050701


async def serializar_gestao_de_usuarios(db: AsyncSession) -> None:
    """Bloqueio até o fim da transação. Quem desativa ou troca o perfil de alguém passa por aqui
    antes de contar os Organizadores ativos, então duas operações simultâneas não deixam o sistema
    sem nenhum. Vem antes de qualquer trava de linha, o que evita impasses."""
    await db.exec(select(func.pg_advisory_xact_lock(BLOQUEIO_GESTAO_DE_ORGANIZADORES)))


async def contar_organizadores_ativos(db: AsyncSession) -> int:
    consulta = select(func.count()).where(
        Usuario.papel == PapelUsuario.ORGANIZADOR, Usuario.ativo.is_(True)
    )
    return (await db.exec(consulta)).one()


async def encerrar_sessoes(db: AsyncSession, usuario_id: UUID) -> int:
    """Soma 1 à versão da sessão no próprio UPDATE (sem ler antes) e devolve o novo valor: os
    tokens emitidos até agora deixam de valer."""
    resultado = await db.exec(
        update(Usuario)
        .where(Usuario.id == usuario_id)
        .values(versao_sessao=Usuario.versao_sessao + 1)
        .returning(Usuario.versao_sessao)
    )
    return resultado.scalar_one()
