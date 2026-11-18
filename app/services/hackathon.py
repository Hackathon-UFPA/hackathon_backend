from datetime import UTC
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, StatusHackathon
from app.controllers.equipe import get_hackathon_by_id
from app.controllers.hackathon import (
    excluir_hackathon,
    get_hackathon_para_atualizar,
    get_nome_da_organizacao,
    listar_hackathons,
    salvar_hackathon,
)
from app.exceptions.convite import hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.hackathon import hackathon_com_dados_ligados, periodo_invalido
from app.models import Hackathon, Usuario
from app.schemas.hackathon import HackathonCreate, HackathonResponse, HackathonUpdate
from app.security.organizacao import mesma_organizacao
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
    if not (
        hackathon.aceita_equipe_estudantes
        or hackathon.aceita_equipe_profissionais
        or hackathon.aceita_equipe_mista
    ):
        periodo_invalido("A edição precisa aceitar ao menos uma categoria de equipe.")
    for inicio, fim, aceita_igual, mensagem in PERIODOS:
        a, b = getattr(hackathon, inicio), getattr(hackathon, fim)
        if a is not None and b is not None and (b < a or (b == a and not aceita_igual)):
            periodo_invalido(mensagem)


def _tratar_integridade(error: IntegrityError):
    mensagem = str(error.orig)
    if "foreign key" in mensagem:
        hackathon_com_dados_ligados()
    erro_de_integridade_sql(error)


def _resposta(hackathon: Hackathon, organizacao_nome: str | None) -> HackathonResponse:
    return HackathonResponse.model_validate(hackathon).model_copy(
        update={"organizacao_nome": organizacao_nome}
    )


async def _com_organizacao(db: AsyncSession, hackathon: Hackathon) -> HackathonResponse:
    return _resposta(hackathon, await get_nome_da_organizacao(db, hackathon.organizacao_id))


async def criar(db: AsyncSession, dados: HackathonCreate, criador: Usuario) -> HackathonResponse:
    """A edição pertence à organização de quem cria."""
    hackathon = Hackathon(**dados.model_dump(), organizacao_id=criador.organizacao_id)
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
    return await _com_organizacao(db, hackathon)


async def editar(db: AsyncSession, hackathon_id: UUID, dados: HackathonUpdate) -> HackathonResponse:
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
    return await _com_organizacao(db, hackathon)


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


async def listar_publicos(
    db: AsyncSession, organizacao_id: UUID | None = None
) -> list[HackathonResponse]:
    """Vitrine: todas as edições, menos os rascunhos, de todas as organizações ou de uma."""
    pares = await listar_hackathons(
        db,
        publicos=True,
        filtrar_organizacao=organizacao_id is not None,
        organizacao_id=organizacao_id,
    )
    return [_resposta(hackathon, nome) for hackathon, nome in pares]


async def listar_da_organizacao(db: AsyncSession, gestor: Usuario) -> list[HackathonResponse]:
    """Painel do gestor: as edições da organização dele, inclusive rascunhos. DEV vê todas."""
    pares = await listar_hackathons(
        db,
        filtrar_organizacao=gestor.papel != PapelUsuario.DEV,
        organizacao_id=gestor.organizacao_id,
    )
    return [_resposta(hackathon, nome) for hackathon, nome in pares]


async def obter_acessivel(
    db: AsyncSession, hackathon_id: UUID, usuario: Usuario | None = None
) -> Hackathon:
    """Rascunho só aparece para a equipe interna da organização dona (e DEV)."""
    hackathon = await get_hackathon_by_id(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    if hackathon.status == StatusHackathon.RASCUNHO and not (
        usuario is not None
        and usuario.papel != PapelUsuario.PARTICIPANTE
        and mesma_organizacao(usuario, hackathon.organizacao_id)
    ):
        hackathon_nao_encontrado()
    return hackathon


async def consultar(
    db: AsyncSession, hackathon_id: UUID, usuario: Usuario | None = None
) -> HackathonResponse:
    hackathon = await obter_acessivel(db, hackathon_id, usuario)
    return await _com_organizacao(db, hackathon)
