from datetime import UTC
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.controllers.hackathon import (
    excluir_hackathon,
    get_hackathon_para_atualizar,
    salvar_hackathon,
)
from app.exceptions.convite import hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.hackathon import hackathon_com_dados_ligados, periodo_invalido
from app.models import Hackathon
from app.schemas.hackathon import HackathonCreate, HackathonUpdate
from app.utils.generic_db_operations import atualizar_instancia
from app.validations.inscricao import como_utc

CAMPOS_DE_DATA = (
    "data_inicio",
    "data_fim",
    "inscricoes_inicio",
    "inscricoes_fim",
    "homologacao_fim",
    "propostas_inicio",
    "propostas_fim",
)

# (início, fim, aceita fim igual ao início, mensagem). Espelha os CHECKs da tabela hackathon.
PERIODOS = (
    ("data_inicio", "data_fim", True, "data_fim não pode ser antes de data_inicio."),
    (
        "inscricoes_inicio",
        "inscricoes_fim",
        False,
        "inscricoes_fim deve ser após inscricoes_inicio.",
    ),
    (
        "inscricoes_fim",
        "homologacao_fim",
        True,
        "homologacao_fim não pode ser antes do fim das inscrições.",
    ),
    ("propostas_inicio", "propostas_fim", False, "propostas_fim deve ser após propostas_inicio."),
)


def _normalizar_datas(hackathon: Hackathon) -> None:
    """As colunas são `timestamp` em UTC: converte para UTC (data sem fuso já é UTC)."""
    for campo in CAMPOS_DE_DATA:
        valor = getattr(hackathon, campo)
        if valor is not None:
            setattr(hackathon, campo, como_utc(valor).astimezone(UTC))


def _validar(hackathon: Hackathon) -> None:
    """Valida o estado final (no PATCH, campos enviados junto com os já gravados)."""
    if hackathon.min_integrantes > hackathon.max_integrantes:
        periodo_invalido("min_integrantes não pode ser maior que max_integrantes.")
    for inicio, fim, aceita_igual, mensagem in PERIODOS:
        a, b = getattr(hackathon, inicio), getattr(hackathon, fim)
        if a is not None and b is not None and (b < a or (b == a and not aceita_igual)):
            periodo_invalido(mensagem)


def _tratar_integridade(error: IntegrityError):
    mensagem = str(error.orig)
    if "foreign key" in mensagem:
        hackathon_com_dados_ligados()
    erro_de_integridade_sql(error)


async def criar(db: AsyncSession, dados: HackathonCreate) -> Hackathon:
    hackathon = Hackathon(**dados.model_dump())
    _normalizar_datas(hackathon)
    _validar(hackathon)
    try:
        await salvar_hackathon(db, hackathon)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(hackathon)
    return hackathon


async def editar(db: AsyncSession, hackathon_id: UUID, dados: HackathonUpdate) -> Hackathon:
    try:
        hackathon = await get_hackathon_para_atualizar(db, hackathon_id)
        if hackathon is None:
            hackathon_nao_encontrado()
        await atualizar_instancia(hackathon, dados)
        _normalizar_datas(hackathon)
        _validar(hackathon)
        await salvar_hackathon(db, hackathon)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(hackathon)
    return hackathon


async def excluir(db: AsyncSession, hackathon_id: UUID) -> None:
    """Só exclui edição sem nada ligado (equipes, temas, termos...). Com dados, a FK recusa e
    a resposta é 409: nesse caso o caminho é mudar o status para CANCELADO."""
    try:
        hackathon = await get_hackathon_para_atualizar(db, hackathon_id)
        if hackathon is None:
            hackathon_nao_encontrado()
        await excluir_hackathon(db, hackathon)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade(error)
    except Exception:
        await db.rollback()
        raise
