from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusAvaliacao, StatusProposta
from app.controllers.avaliacao import (
    get_minha_avaliacao,
    listar_notas,
    salvar_avaliacao,
    substituir_notas,
)
from app.controllers.designacao_avaliacao import get_submissao_by_id, get_submissao_designada
from app.controllers.hackathon import get_hackathon_para_atualizar
from app.controllers.rubrica import get_rubrica_do_hackathon, listar_criterios
from app.exceptions.avaliacao import (
    avaliacao_enviada,
    avaliacao_invalida,
    avaliacao_nao_encontrada,
    proposta_nao_encontrada,
    proposta_nao_enviada,
    rubrica_indisponivel,
)
from app.exceptions.db import erro_de_integridade_sql
from app.models import Avaliacao, CriterioRubrica, NotaCriterioAvaliacao, Usuario
from app.schemas.avaliacao import (
    AvaliacaoRascunho,
    AvaliacaoResponse,
    NotaCriterio,
)
from app.services.resultado import exigir_resultado_aberto


def calcular_nota(criterios: list[CriterioRubrica], notas: list[NotaCriterio]) -> Decimal:
    """Hipótese 0 a 10 a validar com Squad 1; arredonda só o total (ROUND_HALF_UP)."""
    por_id = {n.criterio_id: n.nota for n in notas}
    with localcontext() as contexto:
        contexto.prec = 50
        total = sum(
            (
                Decimal(10)
                * (por_id[c.id] - Decimal(c.escala_min))
                / Decimal(c.escala_max - c.escala_min)
                * c.peso
                / Decimal(100)
                for c in criterios
            ),
            Decimal(0),
        )
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validar(
    dados: AvaliacaoRascunho, criterios: list[CriterioRubrica], *, definitivo: bool
) -> None:
    por_id = {c.id: c for c in criterios}
    ids = [n.criterio_id for n in dados.notas]
    if len(ids) != len(set(ids)):
        avaliacao_invalida("Não repita critérios na avaliação.")
    for nota in dados.notas:
        criterio = por_id.get(nota.criterio_id)
        if criterio is None:
            avaliacao_invalida("Critério inexistente ou fora da rubrica publicada desta proposta.")
        if not nota.nota.is_finite() or not criterio.escala_min <= nota.nota <= criterio.escala_max:
            avaliacao_invalida(f"Nota fora da escala do critério {criterio.id}.")
    if definitivo:
        if not criterios or set(ids) != set(por_id):
            avaliacao_invalida("Informe uma nota para todos os critérios da rubrica.")
        if not dados.parecer or not dados.parecer.strip():
            avaliacao_invalida("Informe um parecer justificado não vazio.")
        if dados.recomendacao is None:
            avaliacao_invalida("Informe a recomendação de APROVACAO ou REPROVACAO.")


async def _resposta(db: AsyncSession, avaliacao: Avaliacao) -> AvaliacaoResponse:
    return AvaliacaoResponse(
        id=avaliacao.id,
        submissao_id=avaliacao.submissao_id,
        avaliador_id=avaliacao.avaliador_id,
        rubrica_id=avaliacao.rubrica_id,
        status=avaliacao.status,
        nota_final=avaliacao.nota,
        parecer=avaliacao.comentarios,
        recomendacao=avaliacao.recomendacao,
        atualizado_em=avaliacao.atualizado_em,
        avaliado_em=avaliacao.avaliado_em,
        notas=[
            NotaCriterio(criterio_id=n.criterio_id, nota=n.nota)
            for n in await listar_notas(db, avaliacao.id)
        ],
    )


async def consultar(db: AsyncSession, avaliador: Usuario, submissao_id: UUID) -> AvaliacaoResponse:
    if await get_submissao_designada(db, submissao_id, avaliador.id) is None:
        proposta_nao_encontrada()
    avaliacao = await get_minha_avaliacao(db, submissao_id, avaliador.id)
    if avaliacao is None:
        avaliacao_nao_encontrada()
    return await _resposta(db, avaliacao)


async def salvar(
    db: AsyncSession,
    avaliador: Usuario,
    submissao_id: UUID,
    dados: AvaliacaoRascunho | None,
    *,
    definitivo: bool = False,
) -> AvaliacaoResponse:
    try:
        # Primeiro confere a designação sem revelar propostas alheias.
        proposta = await get_submissao_designada(
            db, submissao_id, avaliador.id, somente_enviada=False
        )
        if proposta is None:
            proposta_nao_encontrada()
        # Mesma ordem da BE-S4-09: hackathon -> proposta -> avaliação/notas.
        # O lock do hackathon também protege a criação quando ainda não existe avaliação.
        await get_hackathon_para_atualizar(db, proposta.hackathon_id)
        # Resultado homologado (RF31) bloqueia novas avaliações e edições de rascunho.
        await exigir_resultado_aberto(db, proposta.hackathon_id)
        proposta = await get_submissao_by_id(db, submissao_id, para_atualizar=True)
        # Revalida após esperar: uma redistribuição pode ter removido o acesso.
        if (
            await get_submissao_designada(db, submissao_id, avaliador.id, somente_enviada=False)
            is None
        ):
            proposta_nao_encontrada()
        avaliacao = await get_minha_avaliacao(db, submissao_id, avaliador.id)
        if avaliacao is not None and (
            avaliacao.status == StatusAvaliacao.ENVIADA
            or avaliacao.nota is not None
            or avaliacao.avaliado_em is not None
        ):
            avaliacao_enviada()
        if proposta.status != StatusProposta.ENVIADA:
            proposta_nao_enviada()
        rubrica = await get_rubrica_do_hackathon(db, proposta.hackathon_id)
        if rubrica is None or rubrica.publicada_em is None:
            rubrica_indisponivel()
        if avaliacao is not None and avaliacao.rubrica_id not in (None, rubrica.id):
            rubrica_indisponivel()
        criterios = await listar_criterios(db, rubrica.id)
        if dados is None:
            if avaliacao is None:
                avaliacao_nao_encontrada()
            dados = AvaliacaoRascunho(
                notas=[
                    NotaCriterio(criterio_id=n.criterio_id, nota=n.nota)
                    for n in await listar_notas(db, avaliacao.id)
                ],
                parecer=avaliacao.comentarios,
                recomendacao=avaliacao.recomendacao,
            )
        _validar(dados, criterios, definitivo=definitivo)
        if avaliacao is None:
            avaliacao = Avaliacao(submissao_id=submissao_id, avaliador_id=avaliador.id)
        avaliacao.rubrica_id = rubrica.id
        avaliacao.comentarios = dados.parecer
        avaliacao.recomendacao = dados.recomendacao
        avaliacao.atualizado_em = datetime.now(UTC)
        if definitivo:
            avaliacao.status = StatusAvaliacao.ENVIADA
            avaliacao.avaliado_em = avaliacao.atualizado_em
            avaliacao.nota = calcular_nota(criterios, dados.notas)
        await salvar_avaliacao(db, avaliacao)
        await substituir_notas(
            db,
            avaliacao.id,
            [
                NotaCriterioAvaliacao(avaliacao_id=avaliacao.id, **n.model_dump())
                for n in dados.notas
            ],
        )
        resposta = await _resposta(db, avaliacao)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return resposta
