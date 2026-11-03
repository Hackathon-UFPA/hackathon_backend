from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.controllers.equipe import get_hackathon_by_id
from app.controllers.rubrica import (
    get_hackathon_para_atualizar,
    get_rubrica_do_hackathon,
    listar_criterios,
    salvar_rubrica,
    substituir_criterios,
)
from app.exceptions.convite import hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.rubrica import (
    fora_do_prazo_de_publicacao,
    rubrica_incompleta,
    rubrica_nao_encontrada,
    rubrica_nao_publicada,
    rubrica_publicada,
)
from app.models import CriterioRubrica, Rubrica
from app.schemas.rubrica import (
    CriterioRubricaResponse,
    RubricaRascunhoResponse,
    RubricaResponse,
    RubricaUpdate,
)
from app.validations.rubrica import pendencias_para_publicar, pode_publicar_no_prazo, soma_dos_pesos


def _resposta(rubrica: Rubrica, criterios: list[CriterioRubrica]) -> RubricaResponse:
    return RubricaResponse(
        id=rubrica.id,
        hackathon_id=rubrica.hackathon_id,
        publicada=rubrica.publicada_em is not None,
        publicada_em=rubrica.publicada_em,
        soma_pesos=soma_dos_pesos(c.peso for c in criterios),
        criterios=[CriterioRubricaResponse.model_validate(c) for c in criterios],
    )


def _resposta_rascunho(
    rubrica: Rubrica, criterios: list[CriterioRubrica]
) -> RubricaRascunhoResponse:
    pendencias = []
    if rubrica.publicada_em is None:
        pendencias = pendencias_para_publicar(
            [c.nome for c in criterios], [c.peso for c in criterios]
        )
    return RubricaRascunhoResponse(
        **_resposta(rubrica, criterios).model_dump(),
        atualizado_em=rubrica.atualizado_em,
        pendencias=pendencias,
    )


def _tratar_integridade(error: IntegrityError):
    if "rubrica_publicada_imutavel" in str(error.orig):
        rubrica_publicada()
    erro_de_integridade_sql(error)


async def consultar_publicada(db: AsyncSession, hackathon_id: UUID) -> RubricaResponse:
    """Visível para qualquer pessoa, sem login (RF17)."""
    if await get_hackathon_by_id(db, hackathon_id) is None:
        hackathon_nao_encontrado()
    rubrica = await get_rubrica_do_hackathon(db, hackathon_id)
    if rubrica is None or rubrica.publicada_em is None:
        rubrica_nao_publicada()
    return _resposta(rubrica, await listar_criterios(db, rubrica.id))


async def consultar_rascunho(db: AsyncSession, hackathon_id: UUID) -> RubricaRascunhoResponse:
    if await get_hackathon_by_id(db, hackathon_id) is None:
        hackathon_nao_encontrado()
    rubrica = await get_rubrica_do_hackathon(db, hackathon_id)
    if rubrica is None:
        rubrica_nao_encontrada()
    return _resposta_rascunho(rubrica, await listar_criterios(db, rubrica.id))


async def salvar(
    db: AsyncSession, hackathon_id: UUID, dados: RubricaUpdate
) -> RubricaRascunhoResponse:
    """Cria a rubrica da edição, se ainda não existe, e substitui a lista de critérios."""
    try:
        if await get_hackathon_para_atualizar(db, hackathon_id) is None:
            hackathon_nao_encontrado()
        agora = datetime.now(UTC)
        rubrica = await get_rubrica_do_hackathon(db, hackathon_id)
        if rubrica is None:
            rubrica = Rubrica(hackathon_id=hackathon_id, criado_em=agora)
        elif rubrica.publicada_em is not None:
            rubrica_publicada()
        rubrica.atualizado_em = agora
        await salvar_rubrica(db, rubrica)
        criterios = [
            CriterioRubrica(**criterio.model_dump(), rubrica_id=rubrica.id, ordem=ordem)
            for ordem, criterio in enumerate(dados.criterios, start=1)
        ]
        await substituir_criterios(db, rubrica.id, criterios)
        resposta = _resposta_rascunho(rubrica, criterios)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade(error)
    except Exception:
        await db.rollback()
        raise
    return resposta


async def publicar(db: AsyncSession, hackathon_id: UUID) -> RubricaResponse:
    """Publica uma única vez; a versão publicada não muda mais (RN09)."""
    try:
        hackathon = await get_hackathon_para_atualizar(db, hackathon_id)
        if hackathon is None:
            hackathon_nao_encontrado()
        rubrica = await get_rubrica_do_hackathon(db, hackathon_id)
        if rubrica is None:
            rubrica_nao_encontrada()
        if rubrica.publicada_em is not None:
            rubrica_publicada()
        agora = datetime.now(UTC)
        if not pode_publicar_no_prazo(hackathon.inscricoes_inicio, agora):
            fora_do_prazo_de_publicacao()
        criterios = await listar_criterios(db, rubrica.id)
        pendencias = pendencias_para_publicar(
            [c.nome for c in criterios], [c.peso for c in criterios]
        )
        if pendencias:
            rubrica_incompleta(pendencias)
        rubrica.publicada_em = agora
        await salvar_rubrica(db, rubrica)
        resposta = _resposta(rubrica, criterios)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade(error)
    except Exception:
        await db.rollback()
        raise
    return resposta
