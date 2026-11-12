"""Homologação do resultado da avaliação científica e divulgação das aprovadas (RF31, RF32).

O resultado consolidado de cada proposta ENVIADA usa só as avaliações dos avaliadores
designados a ela. Antes da homologação ele é calculado na hora, para o Organizador revisar;
na homologação vira um retrato imutável (`resultados_proposta`), que é o que a consulta
pública e a consulta administrativa leem dali em diante.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import RecomendacaoAvaliacao, StatusAvaliacao
from app.const.resultado import CodigoPendenciaResultado
from app.controllers.hackathon import get_hackathon_para_atualizar
from app.controllers.resultado import (
    DesignacaoComAvaliacao,
    adicionar_homologacao,
    get_homologacao,
    get_nome_usuario,
    get_resultado_da_equipe,
    listar_aprovadas,
    listar_designacoes_com_avaliacao,
    listar_propostas_com_equipe_e_tema,
    listar_resultados,
)
from app.controllers.rubrica import get_rubrica_do_hackathon, listar_criterios
from app.exceptions.convite import hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.resultado import (
    aprovadas_invalidas,
    avaliacoes_nao_concluidas,
    resultado_da_equipe_nao_encontrado,
    resultado_ja_homologado,
)
from app.models import Hackathon, HomologacaoResultado, ResultadoProposta, Usuario
from app.schemas.resultado import (
    PendenciaResultadoResponse,
    PropostaAprovadaResponse,
    PropostasAprovadasResponse,
    ResultadoAvaliacaoResponse,
    ResultadoEquipeResponse,
    ResultadoPropostaResponse,
)
from app.services.email_eventos import avisar_resultado
from app.services.equipe import consultar
from app.services.notificacao import criar_notificacoes_do_resultado, pareceres_da_proposta
from app.validations.inscricao import como_utc


def media_das_notas(notas: list[Decimal]) -> Decimal | None:
    """Média simples das notas finais, arredondada só no fim (duas casas, HALF_UP)."""
    if not notas:
        return None
    with localcontext() as contexto:
        contexto.prec = 50
        media = sum(notas, Decimal(0)) / Decimal(len(notas))
        return media.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class _Consolidado:
    submissao_id: UUID
    equipe_id: UUID
    equipe_nome: str | None
    tema_titulo: str | None
    titulo: str | None
    enviado_em: datetime | None
    designados: int = 0
    notas: list[Decimal] = field(default_factory=list)
    incompletas: int = 0
    aprovacao: int = 0
    reprovacao: int = 0
    classificacao: int | None = None

    @property
    def nota_media(self) -> Decimal | None:
        return media_das_notas(self.notas)


def _classificar(propostas: list[_Consolidado]) -> None:
    """Maior média primeiro; empate: mais recomendações de aprovação, depois quem enviou
    antes, depois o id (resultado determinístico). Sem nota, fica sem classificação."""
    com_nota = [p for p in propostas if p.nota_media is not None]
    com_nota.sort(
        key=lambda p: (
            -p.nota_media,
            -p.aprovacao,
            p.enviado_em or datetime.max,
            str(p.submissao_id),
        )
    )
    for posicao, proposta in enumerate(com_nota, start=1):
        proposta.classificacao = posicao


def _avaliacao_completa(
    designacao: DesignacaoComAvaliacao, rubrica_id: UUID | None, total_criterios: int
) -> bool:
    """RF30: nota final, recomendação, parecer não vazio e nota em todos os critérios da
    rubrica publicada da edição. Avaliação legada (migrada como ENVIADA sem rubrica, notas por
    critério ou recomendação) não passa: precisa ser concluída antes de homologar."""
    return (
        designacao.nota is not None
        and designacao.recomendacao is not None
        and bool(designacao.parecer and designacao.parecer.strip())
        and rubrica_id is not None
        and designacao.rubrica_id == rubrica_id
        and total_criterios > 0
        and designacao.notas_por_criterio == total_criterios
    )


async def _consolidar(
    db: AsyncSession, hackathon: Hackathon, agora: datetime | None = None
) -> tuple[list[_Consolidado], list[PendenciaResultadoResponse]]:
    """Calcula o resultado de cada proposta ENVIADA e lista o que impede homologar."""
    propostas = {
        submissao.id: _Consolidado(
            submissao_id=submissao.id,
            equipe_id=submissao.equipe_id,
            equipe_nome=equipe_nome,
            tema_titulo=tema_titulo,
            titulo=submissao.titulo,
            enviado_em=submissao.enviado_em,
        )
        for submissao, equipe_nome, tema_titulo in await listar_propostas_com_equipe_e_tema(
            db, hackathon.id
        )
    }
    rubrica = await get_rubrica_do_hackathon(db, hackathon.id)
    rubrica_id = rubrica.id if rubrica is not None and rubrica.publicada_em is not None else None
    total_criterios = len(await listar_criterios(db, rubrica_id)) if rubrica_id else 0
    for designacao in await listar_designacoes_com_avaliacao(db, hackathon.id):
        proposta = propostas.get(designacao.submissao_id)
        if proposta is None:  # designação de proposta que não está ENVIADA
            continue
        proposta.designados += 1
        if designacao.status != StatusAvaliacao.ENVIADA:
            continue
        if not _avaliacao_completa(designacao, rubrica_id, total_criterios):
            proposta.incompletas += 1
            continue
        proposta.notas.append(Decimal(designacao.nota))
        if designacao.recomendacao == RecomendacaoAvaliacao.APROVACAO:
            proposta.aprovacao += 1
        elif designacao.recomendacao == RecomendacaoAvaliacao.REPROVACAO:
            proposta.reprovacao += 1

    lista = list(propostas.values())
    _classificar(lista)
    lista.sort(key=lambda p: (p.classificacao is None, p.classificacao or 0, str(p.submissao_id)))

    pendencias: list[PendenciaResultadoResponse] = []
    fim = hackathon.propostas_fim
    if fim is None or como_utc(agora or datetime.now(UTC)) <= como_utc(fim):
        pendencias.append(
            PendenciaResultadoResponse(
                codigo=CodigoPendenciaResultado.PRAZO_DE_PROPOSTAS_ABERTO,
                mensagem=(
                    "O prazo de envio de propostas não está configurado ou ainda não terminou: "
                    "homologar agora deixaria de fora propostas enviadas dentro do prazo."
                ),
            )
        )
    n = hackathon.avaliadores_por_proposta
    if n is None:
        pendencias.append(
            PendenciaResultadoResponse(
                codigo=CodigoPendenciaResultado.QUANTIDADE_NAO_CONFIGURADA,
                mensagem="Configure a quantidade de avaliadores por proposta e distribua.",
            )
        )
    if not lista:
        pendencias.append(
            PendenciaResultadoResponse(
                codigo=CodigoPendenciaResultado.SEM_PROPOSTAS,
                mensagem="O hackathon não tem propostas enviadas para homologar.",
            )
        )
    for proposta in lista:
        nome = proposta.titulo or str(proposta.submissao_id)
        if proposta.designados == 0 or (n is not None and proposta.designados < n):
            pendencias.append(
                PendenciaResultadoResponse(
                    codigo=CodigoPendenciaResultado.AVALIADORES_INSUFICIENTES,
                    mensagem=(
                        f"A proposta '{nome}' tem {proposta.designados} avaliador(es) "
                        f"designado(s) e precisa de {n or 'pelo menos 1'}."
                    ),
                    submissao_id=proposta.submissao_id,
                )
            )
        if proposta.incompletas:
            pendencias.append(
                PendenciaResultadoResponse(
                    codigo=CodigoPendenciaResultado.AVALIACAO_INCOMPLETA,
                    mensagem=(
                        f"A proposta '{nome}' tem {proposta.incompletas} avaliação(ões) enviada(s) "
                        "sem nota em todos os critérios da rubrica publicada, recomendação ou "
                        "parecer (inclui avaliações legadas): conclua-as antes de homologar."
                    ),
                    submissao_id=proposta.submissao_id,
                )
            )
        faltam = proposta.designados - len(proposta.notas) - proposta.incompletas
        if faltam > 0:
            pendencias.append(
                PendenciaResultadoResponse(
                    codigo=CodigoPendenciaResultado.AVALIACAO_PENDENTE,
                    mensagem=(
                        f"A proposta '{nome}' tem {faltam} de {proposta.designados} "
                        "avaliações ainda não enviadas."
                    ),
                    submissao_id=proposta.submissao_id,
                )
            )
    return lista, pendencias


async def _resposta_homologada(
    db: AsyncSession, hackathon: Hackathon, homologacao: HomologacaoResultado
) -> ResultadoAvaliacaoResponse:
    resultados = await listar_resultados(db, homologacao.id)
    return ResultadoAvaliacaoResponse(
        hackathon_id=hackathon.id,
        avaliadores_por_proposta=hackathon.avaliadores_por_proposta,
        homologado=True,
        homologado_em=homologacao.homologado_em,
        homologado_por=homologacao.homologado_por,
        homologado_por_nome=await get_nome_usuario(db, homologacao.homologado_por),
        pode_homologar=False,
        pendencias=[],
        total_propostas=homologacao.total_propostas,
        total_aprovadas=homologacao.total_aprovadas,
        propostas=[
            ResultadoPropostaResponse(
                submissao_id=r.submissao_id,
                equipe_id=r.equipe_id,
                equipe_nome=r.equipe_nome,
                tema_titulo=r.tema_titulo,
                titulo=r.titulo,
                avaliadores_designados=r.avaliacoes,
                avaliacoes_enviadas=r.avaliacoes,
                nota_media=r.nota_media,
                classificacao=r.classificacao,
                recomendacoes_aprovacao=r.recomendacoes_aprovacao,
                recomendacoes_reprovacao=r.recomendacoes_reprovacao,
                aprovada=r.aprovada,
            )
            for r in resultados
        ],
    )


async def consultar_resultado(db: AsyncSession, hackathon_id: UUID) -> ResultadoAvaliacaoResponse:
    """RF31: notas consolidadas e classificação. Depois de homologado, devolve o retrato."""
    hackathon = await db.get(Hackathon, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    homologacao = await get_homologacao(db, hackathon_id)
    if homologacao is not None:
        return await _resposta_homologada(db, hackathon, homologacao)

    propostas, pendencias = await _consolidar(db, hackathon)
    return ResultadoAvaliacaoResponse(
        hackathon_id=hackathon.id,
        avaliadores_por_proposta=hackathon.avaliadores_por_proposta,
        homologado=False,
        pode_homologar=not pendencias,
        pendencias=pendencias,
        total_propostas=len(propostas),
        propostas=[
            ResultadoPropostaResponse(
                submissao_id=p.submissao_id,
                equipe_id=p.equipe_id,
                equipe_nome=p.equipe_nome,
                tema_titulo=p.tema_titulo,
                titulo=p.titulo,
                avaliadores_designados=p.designados,
                avaliacoes_enviadas=len(p.notas),
                nota_media=p.nota_media,
                classificacao=p.classificacao,
                recomendacoes_aprovacao=p.aprovacao,
                recomendacoes_reprovacao=p.reprovacao,
            )
            for p in propostas
        ],
    )


async def homologar(
    db: AsyncSession, organizador: Usuario, hackathon_id: UUID, aprovadas: list[UUID]
) -> ResultadoAvaliacaoResponse:
    """RF31: oficializa o resultado. Exige todas as avaliações concluídas; depois disso o
    resultado, as avaliações e as designações do hackathon ficam bloqueados."""
    try:
        # Mesmo lock da distribuição e da avaliação: nenhuma avaliação muda no meio.
        hackathon = await get_hackathon_para_atualizar(db, hackathon_id)
        if hackathon is None:
            hackathon_nao_encontrado()
        if await get_homologacao(db, hackathon.id) is not None:
            resultado_ja_homologado()
        propostas, pendencias = await _consolidar(db, hackathon)
        if pendencias:
            avaliacoes_nao_concluidas(len(pendencias))

        if len(set(aprovadas)) != len(aprovadas):
            aprovadas_invalidas("Não repita propostas na lista de aprovadas.")
        aprovadas_ids = set(aprovadas)
        if not aprovadas_ids <= {p.submissao_id for p in propostas}:
            aprovadas_invalidas(
                "Toda proposta aprovada precisa ser uma proposta ENVIADA deste hackathon."
            )

        homologacao = HomologacaoResultado(
            hackathon_id=hackathon.id,
            homologado_por=organizador.id,
            total_propostas=len(propostas),
            total_aprovadas=len(aprovadas_ids),
        )
        resultados = [
            ResultadoProposta(
                homologacao_id=homologacao.id,
                hackathon_id=hackathon.id,
                submissao_id=p.submissao_id,
                equipe_id=p.equipe_id,
                equipe_nome=p.equipe_nome,
                tema_titulo=p.tema_titulo,
                titulo=p.titulo,
                nota_media=p.nota_media,
                classificacao=p.classificacao,
                avaliacoes=len(p.notas),
                recomendacoes_aprovacao=p.aprovacao,
                recomendacoes_reprovacao=p.reprovacao,
                aprovada=p.submissao_id in aprovadas_ids,
            )
            for p in propostas
        ]
        adicionar_homologacao(db, homologacao, resultados)
        # RF33: na mesma transação. Se não der para notificar, a homologação não vale.
        await criar_notificacoes_do_resultado(db, resultados)
        await avisar_resultado(db, resultados)
        await db.flush()
        await db.refresh(homologacao)
        resposta = await _resposta_homologada(db, hackathon, homologacao)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return resposta


async def exigir_resultado_aberto(db: AsyncSession, hackathon_id: UUID) -> None:
    """Chamado com o hackathon travado: depois da homologação nada da avaliação muda (RF31)."""
    if await get_homologacao(db, hackathon_id) is not None:
        resultado_ja_homologado()


async def listar_propostas_aprovadas(
    db: AsyncSession, hackathon_id: UUID
) -> PropostasAprovadasResponse:
    """RF32: público. Antes da homologação a lista vem vazia e `divulgado = false`."""
    hackathon = await db.get(Hackathon, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    homologacao = await get_homologacao(db, hackathon_id)
    if homologacao is None:
        return PropostasAprovadasResponse(
            hackathon_id=hackathon.id, hackathon_nome=hackathon.nome, divulgado=False, propostas=[]
        )
    return PropostasAprovadasResponse(
        hackathon_id=hackathon.id,
        hackathon_nome=hackathon.nome,
        divulgado=True,
        divulgado_em=homologacao.homologado_em,
        propostas=[
            PropostaAprovadaResponse(
                submissao_id=r.submissao_id,
                equipe=r.equipe_nome,
                tema=r.tema_titulo,
                titulo=r.titulo,
            )
            for r in await listar_aprovadas(db, homologacao.id)
        ],
    )


async def consultar_resultado_da_equipe(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID
) -> ResultadoEquipeResponse:
    """RF33, RF34: a equipe vê se a proposta foi aprovada e os pareceres, sem identificar os
    avaliadores e sem nota média nem classificação. Só integrantes (e DEV)."""
    equipe = await consultar(db, usuario, equipe_id)
    homologacao = await get_homologacao(db, equipe.hackathon_id)
    if homologacao is None:
        return ResultadoEquipeResponse(
            equipe_id=equipe.id,
            hackathon_id=equipe.hackathon_id,
            divulgado=False,
            somente_leitura=False,
            pareceres=[],
        )
    resultado = await get_resultado_da_equipe(db, homologacao.id, equipe.id)
    if resultado is None:
        resultado_da_equipe_nao_encontrado()
    return ResultadoEquipeResponse(
        equipe_id=equipe.id,
        hackathon_id=equipe.hackathon_id,
        divulgado=True,
        divulgado_em=homologacao.homologado_em,
        submissao_id=resultado.submissao_id,
        titulo=resultado.titulo,
        aprovada=resultado.aprovada,
        somente_leitura=not resultado.aprovada,
        pareceres=await pareceres_da_proposta(db, resultado.submissao_id),
    )
