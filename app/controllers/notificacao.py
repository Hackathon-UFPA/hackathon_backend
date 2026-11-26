from uuid import UUID

from sqlalchemy import func, literal_column, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoNotificacao
from app.models import Notificacao, NotificacaoResultado

AGORA_UTC = literal_column("(now() AT TIME ZONE 'utc')")


def adicionar_notificacoes(db: AsyncSession, notificacoes: list[NotificacaoResultado]) -> None:
    db.add_all(notificacoes)


def adicionar_notificacoes_centrais(db: AsyncSession, notificacoes: list[Notificacao]) -> None:
    db.add_all(notificacoes)


async def inserir_ignorando_repetidas(db: AsyncSession, valores: list[dict]) -> int:
    """Grava sem commit. Um aviso com a mesma (usuário, chave) já gravado é ignorado, mesmo
    com duas transações ao mesmo tempo (a unicidade é do banco). Devolve quantos criou."""
    if not valores:
        return 0
    comando = (
        insert(Notificacao)
        .values(valores)
        .on_conflict_do_nothing(index_elements=["usuario_id", "chave_idempotencia"])
        .returning(col(Notificacao.id))
    )
    return len((await db.exec(comando)).all())


def _filtrar(consulta, usuario_id: UUID, lida: bool | None, tipo: TipoNotificacao | None):
    consulta = consulta.where(Notificacao.usuario_id == usuario_id)
    if lida is True:
        consulta = consulta.where(col(Notificacao.lida_em).is_not(None))
    elif lida is False:
        consulta = consulta.where(col(Notificacao.lida_em).is_(None))
    if tipo is not None:
        consulta = consulta.where(Notificacao.tipo == tipo)
    return consulta


def _com_resultado():
    return select(Notificacao, NotificacaoResultado).join(
        NotificacaoResultado,
        col(NotificacaoResultado.id) == col(Notificacao.notificacao_resultado_id),
        isouter=True,
    )


async def listar_notificacoes_do_usuario(
    db: AsyncSession,
    usuario_id: UUID,
    *,
    lida: bool | None = None,
    tipo: TipoNotificacao | None = None,
    limite: int,
    deslocamento: int,
) -> list[tuple[Notificacao, NotificacaoResultado | None]]:
    """Mais recentes primeiro; o id desempata para a ordem ser determinística."""
    consulta = (
        _filtrar(_com_resultado(), usuario_id, lida, tipo)
        .order_by(col(Notificacao.criado_em).desc(), col(Notificacao.id))
        .limit(limite)
        .offset(deslocamento)
    )
    return [(n, r) for n, r in (await db.exec(consulta)).all()]


async def contar_notificacoes(
    db: AsyncSession,
    usuario_id: UUID,
    *,
    lida: bool | None = None,
    tipo: TipoNotificacao | None = None,
) -> int:
    consulta = _filtrar(select(func.count(col(Notificacao.id))), usuario_id, lida, tipo)
    return (await db.exec(consulta)).one()


async def get_notificacao_do_usuario(
    db: AsyncSession, usuario_id: UUID, notificacao_id: UUID
) -> tuple[Notificacao, NotificacaoResultado | None] | None:
    consulta = _com_resultado().where(
        Notificacao.id == notificacao_id, Notificacao.usuario_id == usuario_id
    )
    linha = (await db.exec(consulta)).first()
    return (linha[0], linha[1]) if linha else None


async def marcar_como_lida(db: AsyncSession, usuario_id: UUID, notificacao_id: UUID) -> bool:
    """Marca uma notificação do usuário (sem commit). Já lida, mantém o `lida_em` original.
    Devolve False se ela não existe ou é de outra pessoa."""
    comando = (
        update(Notificacao)
        .where(Notificacao.id == notificacao_id, Notificacao.usuario_id == usuario_id)
        .values(lida_em=func.coalesce(Notificacao.lida_em, AGORA_UTC))
        .returning(col(Notificacao.id))
    )
    return (await db.exec(comando)).first() is not None


async def marcar_todas_como_lidas(db: AsyncSession, usuario_id: UUID) -> int:
    comando = (
        update(Notificacao)
        .where(Notificacao.usuario_id == usuario_id, col(Notificacao.lida_em).is_(None))
        .values(lida_em=AGORA_UTC)
        .returning(col(Notificacao.id))
    )
    return len((await db.exec(comando)).all())


async def marcar_do_convite_como_lidas(db: AsyncSession, usuario_id: UUID, convite_id: UUID) -> int:
    """Marca como lidas (sem commit) as notificações de um convite para a pessoa: a original
    (`convite:{id}`) e as dos reenvios (`convite:{id}:envio:{n}`). Já lidas mantêm o `lida_em`."""
    chave = col(Notificacao.chave_idempotencia)
    comando = (
        update(Notificacao)
        .where(
            Notificacao.usuario_id == usuario_id,
            (chave == f"convite:{convite_id}") | chave.like(f"convite:{convite_id}:envio:%"),
            col(Notificacao.lida_em).is_(None),
        )
        .values(lida_em=AGORA_UTC)
        .returning(col(Notificacao.id))
    )
    return len((await db.exec(comando)).all())
