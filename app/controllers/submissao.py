from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Submissao, Tema
from app.schemas.submissao import SubmissaoUpdate
from app.utils.generic_db_operations import atualizar_instancia


async def get_submissao_da_equipe(
    db: AsyncSession, equipe_id: UUID, *, para_atualizar: bool = False
) -> Submissao | None:
    consulta = select(Submissao).where(Submissao.equipe_id == equipe_id)
    if para_atualizar:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def get_tema_by_id(db: AsyncSession, tema_id: UUID) -> Tema | None:
    return await db.get(Tema, tema_id)


async def criar_submissao(db: AsyncSession, submissao: Submissao) -> Submissao:
    db.add(submissao)
    await db.flush()
    return submissao


async def atualizar_submissao(
    db: AsyncSession, submissao: Submissao, dados: SubmissaoUpdate
) -> Submissao:
    await atualizar_instancia(submissao, dados)
    db.add(submissao)
    await db.flush()
    return submissao
