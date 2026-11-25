"""Painel do mentor (BE-S6-04, RF41): acompanhamento das equipes designadas, somente leitura.

A visibilidade de equipes não designadas depende da Q24. Até a decisão, o mentor só enxerga as
equipes que acompanha hoje."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon, TipoMarcoMentoria
from app.controllers import painel_mentor as controller
from app.controllers.membro_equipe import listar_membros_com_usuario
from app.exceptions.convite import equipe_nao_encontrada
from app.models import (
    AtribuicaoMentor,
    EntregaMentoria,
    Equipe,
    Hackathon,
    MarcoMentoria,
    Usuario,
)
from app.schemas.painel_mentor import (
    DetalheEquipeNoPainel,
    EntregaNoPainel,
    EquipeNoPainel,
    IntegranteNoPainel,
    MarcoNoPainel,
    PainelMentorResponse,
    ProgressoMarcos,
    ProximoMarco,
    ResumoPainel,
    SituacaoMarcoEquipe,
)
from app.services.conteudo import agora_utc

EDICOES_ENCERRADAS = (StatusHackathon.FINALIZADO, StatusHackathon.CANCELADO)


@dataclass(frozen=True)
class AndamentoMarco:
    marco: MarcoMentoria
    entrega: EntregaMentoria | None
    situacao: SituacaoMarcoEquipe | None


@dataclass(frozen=True)
class Acompanhamento:
    """Uma equipe designada, com o andamento dela em cada marco da edição."""

    atribuicao: AtribuicaoMentor
    equipe: Equipe
    hackathon: Hackathon
    marcos: list[AndamentoMarco]


def situacao_do_marco(
    marco: MarcoMentoria,
    entrega: EntregaMentoria | None,
    *,
    edicao_encerrada: bool,
    agora: datetime,
) -> SituacaoMarcoEquipe | None:
    """O prazo é inclusivo, como no envio da entrega. O marco final sem registro fica sem
    situação: o envio dele pertence à submissão final (BE-S6-07)."""
    if entrega is not None:
        return SituacaoMarcoEquipe.ENTREGUE
    if marco.tipo == TipoMarcoMentoria.FINAL:
        return None
    if edicao_encerrada or agora > marco.data_limite:
        return SituacaoMarcoEquipe.NAO_ENTREGUE
    return SituacaoMarcoEquipe.PENDENTE


async def _acompanhamentos(
    db: AsyncSession,
    mentor: Usuario,
    *,
    hackathon_id: UUID | None = None,
    equipe_id: UUID | None = None,
) -> list[Acompanhamento]:
    """Carrega equipes, marcos e entregas em três consultas, qualquer que seja a quantidade."""
    vinculos = await controller.equipes_acompanhadas(
        db, mentor.id, mentor.organizacao_id, hackathon_id=hackathon_id, equipe_id=equipe_id
    )
    if not vinculos:
        return []
    marcos_por_edicao: defaultdict[UUID, list[MarcoMentoria]] = defaultdict(list)
    for marco in await controller.marcos_das_edicoes(db, {h.id for _, _, h in vinculos}):
        marcos_por_edicao[marco.hackathon_id].append(marco)
    entregas = {
        (entrega.equipe_id, entrega.marco_id): entrega
        for entrega in await controller.entregas_das_equipes(db, {e.id for _, e, _ in vinculos})
    }
    agora = agora_utc()

    def andamento(equipe: Equipe, hackathon: Hackathon, marco: MarcoMentoria) -> AndamentoMarco:
        entrega = entregas.get((equipe.id, marco.id))
        situacao = situacao_do_marco(
            marco,
            entrega,
            edicao_encerrada=hackathon.status in EDICOES_ENCERRADAS,
            agora=agora,
        )
        return AndamentoMarco(marco, entrega, situacao)

    return [
        Acompanhamento(
            atribuicao,
            equipe,
            hackathon,
            [andamento(equipe, hackathon, marco) for marco in marcos_por_edicao[hackathon.id]],
        )
        for atribuicao, equipe, hackathon in vinculos
    ]


def _progresso(marcos: list[AndamentoMarco]) -> ProgressoMarcos:
    contagem = Counter(m.situacao for m in marcos if m.marco.tipo == TipoMarcoMentoria.PARCIAL)
    return ProgressoMarcos(
        total=contagem.total(),
        entregues=contagem[SituacaoMarcoEquipe.ENTREGUE],
        pendentes=contagem[SituacaoMarcoEquipe.PENDENTE],
        nao_entregues=contagem[SituacaoMarcoEquipe.NAO_ENTREGUE],
    )


def _equipe_no_painel(item: Acompanhamento) -> EquipeNoPainel:
    # Os marcos chegam na ordem do calendário: o primeiro pendente é o de prazo mais próximo.
    proximo = next(
        (m.marco for m in item.marcos if m.situacao == SituacaoMarcoEquipe.PENDENTE), None
    )
    return EquipeNoPainel(
        equipe_id=item.equipe.id,
        equipe_nome=item.equipe.nome,
        categoria=item.equipe.categoria,
        hackathon_id=item.hackathon.id,
        hackathon_nome=item.hackathon.nome,
        hackathon_status=item.hackathon.status,
        atribuicao_id=item.atribuicao.id,
        atribuido_em=item.atribuicao.atribuido_em,
        progresso=_progresso(item.marcos),
        proximo_marco=ProximoMarco.model_validate(proximo) if proximo else None,
    )


def _resumo(equipes: list[EquipeNoPainel]) -> ResumoPainel:
    return ResumoPainel(
        **{
            campo: sum(getattr(equipe.progresso, campo) for equipe in equipes)
            for campo in ProgressoMarcos.model_fields
        },
        equipes_com_nao_entregues=sum(equipe.progresso.nao_entregues > 0 for equipe in equipes),
    )


def _marco_no_painel(item: AndamentoMarco) -> MarcoNoPainel:
    marco = item.marco
    return MarcoNoPainel(
        id=marco.id,
        titulo=marco.titulo,
        descricao=marco.descricao,
        data_limite=marco.data_limite,
        ordem=marco.ordem,
        tipo=marco.tipo,
        situacao=item.situacao,
        entrega=EntregaNoPainel.model_validate(item.entrega) if item.entrega else None,
    )


async def painel(
    db: AsyncSession,
    mentor: Usuario,
    hackathon_id: UUID | None,
    equipe_id: UUID | None,
    limite: int,
    deslocamento: int,
) -> PainelMentorResponse:
    """Filtro por equipe ou edição fora do escopo devolve painel vazio, sem revelar se existe."""
    acompanhamentos = await _acompanhamentos(
        db, mentor, hackathon_id=hackathon_id, equipe_id=equipe_id
    )
    equipes = [_equipe_no_painel(item) for item in acompanhamentos]
    return PainelMentorResponse(
        total=len(equipes),
        limite=limite,
        deslocamento=deslocamento,
        resumo=_resumo(equipes),
        equipes=equipes[deslocamento : deslocamento + limite],
    )


async def detalhar_equipe(
    db: AsyncSession, mentor: Usuario, equipe_id: UUID
) -> DetalheEquipeNoPainel:
    """Equipe inexistente ou fora do escopo responde o mesmo 404."""
    acompanhamentos = await _acompanhamentos(db, mentor, equipe_id=equipe_id)
    if not acompanhamentos:
        equipe_nao_encontrada()
    item = acompanhamentos[0]
    return DetalheEquipeNoPainel(
        **_equipe_no_painel(item).model_dump(),
        integrantes=[
            IntegranteNoPainel(nome=usuario.nome, funcao=membro.funcao)
            for membro, usuario in await listar_membros_com_usuario(db, equipe_id)
        ],
        marcos=[_marco_no_painel(marco) for marco in item.marcos],
    )
