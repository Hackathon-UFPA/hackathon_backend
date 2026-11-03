from uuid import UUID

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Submissao, Tema
from app.schemas.tema import TemaUpdate
from app.utils.generic_db_operations import atualizar_instancia


async def get_tema_by_id(
    db: AsyncSession, tema_id: UUID, *, para_atualizar: bool = False
) -> Tema | None:
    if not para_atualizar:
        return await db.get(Tema, tema_id)
    consulta = select(Tema).where(Tema.id == tema_id).with_for_update()
    return (await db.exec(consulta)).first()


async def listar_temas(db: AsyncSession, hackathon_id: UUID, *, apenas_ativos: bool) -> list[Tema]:
    consulta = select(Tema).where(Tema.hackathon_id == hackathon_id)
    if apenas_ativos:
        consulta = consulta.where(col(Tema.ativo).is_(True))
    return list((await db.exec(consulta.order_by(Tema.titulo))).all())


async def tema_tem_propostas(db: AsyncSession, tema_id: UUID) -> bool:
    """Qualquer proposta conta, inclusive rascunho (RN04)."""
    consulta = select(func.count()).select_from(Submissao).where(Submissao.tema_id == tema_id)
    return (await db.exec(consulta)).one() > 0


async def criar_tema(db: AsyncSession, tema: Tema) -> Tema:
    db.add(tema)
    await db.flush()
    return tema


async def atualizar_tema(db: AsyncSession, tema: Tema, dados: TemaUpdate) -> Tema:
    await atualizar_instancia(tema, dados)
    db.add(tema)
    await db.flush()
    return tema


async def excluir_tema(db: AsyncSession, tema: Tema) -> None:
    await db.delete(tema)
    await db.flush()
