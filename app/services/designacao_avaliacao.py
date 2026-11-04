from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon, StatusProposta
from app.controllers.designacao_avaliacao import (
    adicionar_designacao,
    contar_carga_por_avaliador,
    contar_elegiveis_entre,
    get_submissao_by_id,
    get_submissao_designada,
    listar_avaliadores_elegiveis,
    listar_designacoes_da_submissao,
    listar_designacoes_do_hackathon,
    listar_enviadas_do_hackathon,
    listar_submissoes_designadas,
    listar_usuarios_por_id,
    remover_designacao,
    submissoes_com_avaliacao,
)
from app.controllers.hackathon import get_hackathon_para_atualizar
from app.exceptions.avaliacao import (
    avaliacao_ja_iniciada,
    avaliadores_insuficientes,
    avaliadores_nao_elegiveis,
    proposta_com_nota,
    proposta_nao_encontrada,
    proposta_nao_enviada,
    quantidade_de_avaliadores_invalida,
    quantidade_nao_configurada,
)
from app.exceptions.convite import hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.models import DesignacaoAvaliacao, Hackathon, Submissao, Usuario
from app.schemas.designacao_avaliacao import (
    AvaliadorDesignadoResponse,
    ConfiguracaoAvaliacaoResponse,
    DistribuicaoResponse,
    PropostaDesignadaAdminResponse,
)

# Depois destes status a avaliação já começou ou o evento acabou (RF29).
STATUS_SEM_DISTRIBUICAO = {
    StatusHackathon.EM_AVALIACAO,
    StatusHackathon.FINALIZADO,
    StatusHackathon.CANCELADO,
}


async def _hackathon_travado(db: AsyncSession, hackathon_id: UUID) -> Hackathon:
    hackathon = await get_hackathon_para_atualizar(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    return hackathon


def _exigir_distribuicao_aberta(hackathon: Hackathon) -> int:
    """Confere o status e devolve a quantidade N de avaliadores por proposta."""
    if hackathon.status in STATUS_SEM_DISTRIBUICAO:
        avaliacao_ja_iniciada()
    if hackathon.avaliadores_por_proposta is None:
        quantidade_nao_configurada()
    return hackathon.avaliadores_por_proposta


async def configurar(
    db: AsyncSession, hackathon_id: UUID, quantidade: int
) -> ConfiguracaoAvaliacaoResponse:
    """Só define o N das próximas distribuições; designações existentes ficam como estão."""
    hackathon = await _hackathon_travado(db, hackathon_id)
    hackathon.avaliadores_por_proposta = quantidade
    db.add(hackathon)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    return ConfiguracaoAvaliacaoResponse(
        hackathon_id=hackathon.id, avaliadores_por_proposta=quantidade
    )


async def distribuir(
    db: AsyncSession, organizador: Usuario, hackathon_id: UUID
) -> DistribuicaoResponse:
    """Completa até N avaliadores cada proposta ENVIADA, sempre com quem tem menos propostas.
    Propostas que já têm N ou mais (ou avaliação iniciada) não são alteradas. Se faltar avaliador
    elegível para qualquer proposta, nada é gravado."""
    try:
        hackathon = await _hackathon_travado(db, hackathon_id)
        n = _exigir_distribuicao_aberta(hackathon)

        propostas = await listar_enviadas_do_hackathon(db, hackathon.id)
        ids = [proposta.id for proposta in propostas]
        com_avaliacao = await submissoes_com_avaliacao(db, ids)
        existentes: dict[UUID, set[UUID]] = {proposta_id: set() for proposta_id in ids}
        for designacao in await listar_designacoes_do_hackathon(db, hackathon.id):
            existentes.setdefault(designacao.submissao_id, set()).add(designacao.avaliador_id)

        elegiveis = [usuario.id for usuario in await listar_avaliadores_elegiveis(db)]
        carga = await contar_carga_por_avaliador(db, hackathon.id)

        novas: list[DesignacaoAvaliacao] = []
        completas = 0
        distribuidas = 0
        for proposta in propostas:
            ja_designados = existentes[proposta.id]
            faltam = n - len(ja_designados)
            if faltam <= 0 or proposta.id in com_avaliacao:
                completas += 1
                continue
            candidatos = sorted(
                (id_ for id_ in elegiveis if id_ not in ja_designados),
                key=lambda id_: (carga.get(id_, 0), str(id_)),
            )
            if len(candidatos) < faltam:
                avaliadores_insuficientes(n, len(elegiveis))
            for avaliador_id in candidatos[:faltam]:
                carga[avaliador_id] = carga.get(avaliador_id, 0) + 1
                novas.append(
                    DesignacaoAvaliacao(
                        submissao_id=proposta.id,
                        hackathon_id=hackathon.id,
                        avaliador_id=avaliador_id,
                        atribuido_por=organizador.id,
                    )
                )
            distribuidas += 1

        for designacao in novas:
            adicionar_designacao(db, designacao)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return DistribuicaoResponse(
        hackathon_id=hackathon_id,
        avaliadores_por_proposta=n,
        propostas_distribuidas=distribuidas,
        designacoes_criadas=len(novas),
        propostas_ja_completas=completas,
    )


async def redistribuir(
    db: AsyncSession,
    organizador: Usuario,
    submissao_id: UUID,
    avaliador_ids: list[UUID],
) -> PropostaDesignadaAdminResponse:
    """Troca os avaliadores de uma proposta pela lista informada (exatamente N, sem repetidos).
    Quem continua na lista mantém a designação original."""
    try:
        proposta = await get_submissao_by_id(db, submissao_id)
        if proposta is None:
            proposta_nao_encontrada()
        # Mesma ordem de locks da distribuição: hackathon antes da proposta
        hackathon = await _hackathon_travado(db, proposta.hackathon_id)
        n = _exigir_distribuicao_aberta(hackathon)
        if proposta.status != StatusProposta.ENVIADA:
            proposta_nao_enviada()
        if await submissoes_com_avaliacao(db, [proposta.id]):
            proposta_com_nota()
        if len(set(avaliador_ids)) != len(avaliador_ids) or len(avaliador_ids) != n:
            quantidade_de_avaliadores_invalida(n)
        if await contar_elegiveis_entre(db, avaliador_ids) != n:
            avaliadores_nao_elegiveis()

        atuais = {d.avaliador_id: d for d in await listar_designacoes_da_submissao(db, proposta.id)}
        for avaliador_id, designacao in atuais.items():
            if avaliador_id not in avaliador_ids:
                await remover_designacao(db, designacao)
        # O delete precisa chegar ao banco antes dos inserts, por causa da unicidade
        await db.flush()
        for avaliador_id in avaliador_ids:
            if avaliador_id not in atuais:
                adicionar_designacao(
                    db,
                    DesignacaoAvaliacao(
                        submissao_id=proposta.id,
                        hackathon_id=hackathon.id,
                        avaliador_id=avaliador_id,
                        atribuido_por=organizador.id,
                    ),
                )
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return (await _agrupar(db, hackathon.id, [proposta]))[0]


async def _agrupar(
    db: AsyncSession, hackathon_id: UUID, propostas: list[Submissao]
) -> list[PropostaDesignadaAdminResponse]:
    designacoes = await listar_designacoes_do_hackathon(db, hackathon_id)
    usuarios = await listar_usuarios_por_id(db, list({d.avaliador_id for d in designacoes}))
    por_proposta: dict[UUID, list[AvaliadorDesignadoResponse]] = {}
    for designacao in designacoes:
        usuario = usuarios[designacao.avaliador_id]
        por_proposta.setdefault(designacao.submissao_id, []).append(
            AvaliadorDesignadoResponse(
                id=usuario.id,
                nome=usuario.nome,
                email=usuario.email,
                atribuido_em=designacao.atribuido_em,
            )
        )
    return [
        PropostaDesignadaAdminResponse(
            submissao_id=proposta.id,
            equipe_id=proposta.equipe_id,
            titulo=proposta.titulo,
            avaliadores=por_proposta.get(proposta.id, []),
        )
        for proposta in propostas
    ]


async def listar_designacoes(
    db: AsyncSession, hackathon_id: UUID
) -> list[PropostaDesignadaAdminResponse]:
    """Cada proposta ENVIADA com os avaliadores designados (lista vazia se ainda não há)."""
    hackathon = await db.get(Hackathon, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    propostas = await listar_enviadas_do_hackathon(db, hackathon_id)
    return await _agrupar(db, hackathon_id, propostas)


async def listar_minhas_propostas(db: AsyncSession, avaliador: Usuario) -> list[Submissao]:
    return await listar_submissoes_designadas(db, avaliador.id)


async def consultar_minha_proposta(
    db: AsyncSession, avaliador: Usuario, submissao_id: UUID
) -> Submissao:
    """Proposta não designada a quem consulta 'não existe': não revela propostas alheias."""
    proposta = await get_submissao_designada(db, submissao_id, avaliador.id)
    if proposta is None:
        proposta_nao_encontrada()
    return proposta
