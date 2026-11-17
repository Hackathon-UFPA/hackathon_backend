from datetime import UTC, datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.exceptions.auth import sem_organizacao
from app.exceptions.organizacao import organizacao_nao_encontrada
from app.models import Organizacao, Usuario
from app.schemas.organizacao import OrganizacaoUpdate


async def consultar(db: AsyncSession, organizacao_id: UUID) -> Organizacao:
    organizacao = await db.get(Organizacao, organizacao_id)
    if organizacao is None:
        organizacao_nao_encontrada()
    return organizacao


async def da_equipe(db: AsyncSession, usuario: Usuario) -> Organizacao:
    if usuario.organizacao_id is None:
        sem_organizacao()
    return await consultar(db, usuario.organizacao_id)


async def editar(db: AsyncSession, usuario: Usuario, dados: OrganizacaoUpdate) -> Organizacao:
    organizacao = await da_equipe(db, usuario)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        if campo == "site" and valor is not None:
            valor = str(valor)
        if campo in ("nome", "tipo") and valor is None:
            continue
        setattr(organizacao, campo, valor)
    organizacao.atualizado_em = datetime.now(UTC)
    db.add(organizacao)
    await db.commit()
    await db.refresh(organizacao)
    return organizacao
