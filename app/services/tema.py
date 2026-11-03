from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.controllers.equipe import get_hackathon_by_id
from app.controllers.tema import (
    atualizar_tema,
    criar_tema,
    excluir_tema,
    get_tema_by_id,
    listar_temas,
    tema_tem_propostas,
)
from app.exceptions.auth import acesso_negado
from app.exceptions.convite import hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.submissao import tema_nao_encontrado
from app.exceptions.tema import tema_com_propostas, titulo_de_tema_repetido
from app.models import Tema, Usuario
from app.schemas.tema import TemaCreate, TemaUpdate
from app.security.permissoes import PERFIS_QUE_GERENCIAM_EDITAL


def gerencia_edital(usuario: Usuario) -> bool:
    return usuario.papel == PapelUsuario.DEV or usuario.papel in PERFIS_QUE_GERENCIAM_EDITAL


def _tratar_integridade(error: IntegrityError):
    mensagem = str(error.orig)
    if "uq_temas_hackathon_titulo" in mensagem:
        titulo_de_tema_repetido()
    if "submissoes" in mensagem and "foreign key" in mensagem:
        tema_com_propostas()
    erro_de_integridade_sql(error)


async def criar(db: AsyncSession, hackathon_id: UUID, dados: TemaCreate) -> Tema:
    if await get_hackathon_by_id(db, hackathon_id) is None:
        hackathon_nao_encontrado()
    agora = datetime.now(UTC)
    tema = Tema(**dados.model_dump(), hackathon_id=hackathon_id, criado_em=agora)
    try:
        await criar_tema(db, tema)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(tema)
    return tema


async def listar(
    db: AsyncSession, usuario: Usuario, hackathon_id: UUID, incluir_inativos: bool
) -> list[Tema]:
    """Temas desativados não aparecem para escolha na proposta (RF15)."""
    if incluir_inativos and not gerencia_edital(usuario):
        acesso_negado()
    if await get_hackathon_by_id(db, hackathon_id) is None:
        hackathon_nao_encontrado()
    return await listar_temas(db, hackathon_id, apenas_ativos=not incluir_inativos)


async def consultar(db: AsyncSession, usuario: Usuario, tema_id: UUID) -> Tema:
    tema = await get_tema_by_id(db, tema_id)
    if tema is None or (not tema.ativo and not gerencia_edital(usuario)):
        tema_nao_encontrado()
    return tema


async def editar(db: AsyncSession, tema_id: UUID, dados: TemaUpdate) -> Tema:
    try:
        tema = await get_tema_by_id(db, tema_id, para_atualizar=True)
        if tema is None:
            tema_nao_encontrado()
        tema.atualizado_em = datetime.now(UTC)
        await atualizar_tema(db, tema, dados)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(tema)
    return tema


async def excluir(db: AsyncSession, tema_id: UUID) -> None:
    """Não exclui tema com propostas ligadas, nem rascunhos (RN04). O FOR UPDATE espera
    propostas que estejam sendo gravadas com este tema."""
    try:
        tema = await get_tema_by_id(db, tema_id, para_atualizar=True)
        if tema is None:
            tema_nao_encontrado()
        if await tema_tem_propostas(db, tema.id):
            tema_com_propostas()
        await excluir_tema(db, tema)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade(error)
    except Exception:
        await db.rollback()
        raise
