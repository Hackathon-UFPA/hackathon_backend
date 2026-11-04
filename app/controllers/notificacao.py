from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import NotificacaoResultado


def adicionar_notificacoes(db: AsyncSession, notificacoes: list[NotificacaoResultado]) -> None:
    db.add_all(notificacoes)


async def listar_notificacoes_do_usuario(
    db: AsyncSession, usuario_id: UUID
) -> list[NotificacaoResultado]:
    """Mais recentes primeiro; o id desempata para a ordem ser determinística."""
    consulta = (
        select(NotificacaoResultado)
        .where(NotificacaoResultado.usuario_id == usuario_id)
        .order_by(col(NotificacaoResultado.criado_em).desc(), col(NotificacaoResultado.id))
    )
    return list((await db.exec(consulta)).all())
