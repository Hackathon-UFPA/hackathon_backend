"""Painel da equipe, conclusão da inscrição e reavaliação da homologação (RF22, RF23, RF25)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FuncaoMembro, PapelUsuario, SituacaoEquipe, TipoProtocolo
from app.controllers.convite import cancelar_convites_pendentes
from app.controllers.equipe import (
    get_equipe_by_id,
    get_hackathon_by_id,
    listar_equipes_para_homologacao,
)
from app.controllers.membro_equipe import get_membro, get_membro_no_hackathon
from app.controllers.protocolo import criar_protocolo
from app.exceptions.convite import (
    apenas_lider_da_equipe,
    equipe_nao_encontrada,
    fora_do_periodo_de_inscricao,
    hackathon_nao_encontrado,
)
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.inscricao import inscricao_ja_concluida, requisitos_nao_cumpridos
from app.models import Equipe, Hackathon, Protocolo, Usuario
from app.schemas.inscricao import (
    ConclusaoInscricaoResponse,
    IntegrantePainelResponse,
    PainelEquipeResponse,
    PendenciaResponse,
    ProtocoloResponse,
    ReavaliacaoResponse,
)
from app.services.equipe import consultar
from app.services.homologacao import avaliar, reavaliar_homologacao
from app.validations.inscricao import inscricoes_abertas


async def _equipe_e_hackathon(
    db: AsyncSession, equipe_id: UUID, *, para_atualizar: bool = False
) -> tuple[Equipe, Hackathon]:
    equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=para_atualizar)
    if equipe is None:
        equipe_nao_encontrada()
    hackathon = await get_hackathon_by_id(db, equipe.hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    return equipe, hackathon


async def _eh_lider(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> bool:
    """Líder técnico = `membros_equipe.funcao = LIDER` (RN03). DEV passa, como nas demais rotas."""
    if usuario.papel == PapelUsuario.DEV:
        return True
    membro = await get_membro(db, equipe_id, usuario.id)
    return membro is not None and membro.funcao == FuncaoMembro.LIDER


async def _protocolo_da_inscricao(db: AsyncSession, equipe_id: UUID) -> Protocolo | None:
    consulta = select(Protocolo).where(
        Protocolo.equipe_id == equipe_id, Protocolo.tipo == TipoProtocolo.INSCRICAO_EQUIPE
    )
    return (await db.exec(consulta)).first()


async def painel(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> PainelEquipeResponse:
    """O que cada integrante já fez, em que pé está a equipe e o que ainda falta (RF25).
    Quem pode ver é quem pode consultar a equipe: integrantes, e DEV."""
    equipe = await consultar(db, usuario, equipe_id)
    hackathon = await get_hackathon_by_id(db, equipe.hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()

    avaliacao = await avaliar(db, equipe, hackathon)
    voce_e_lider = await _eh_lider(db, usuario, equipe.id)
    protocolo = await _protocolo_da_inscricao(db, equipe.id)

    integrantes = [
        IntegrantePainelResponse(
            usuario_id=item.usuario.id,
            nome=item.usuario.nome,
            email=item.usuario.email,
            funcao=item.membro.funcao,
            integrante=True,
            convite=item.convite,
            termos_aceitos=item.termos_aceitos,
            comprovante=item.comprovante,
        )
        for item in avaliacao.integrantes
    ] + [
        IntegrantePainelResponse(
            usuario_id=convite.usuario_id,
            nome=convite.nome,
            email=convite.email,
            integrante=False,
            convite=convite.status,
            termos_aceitos=False,
        )
        for convite in avaliacao.convites_em_aberto
    ]

    return PainelEquipeResponse(
        equipe_id=equipe.id,
        hackathon_id=hackathon.id,
        nome=equipe.nome,
        situacao=equipe.situacao,
        inscricao_concluida_em=equipe.inscricao_concluida_em,
        homologada_em=equipe.homologada_em,
        protocolo=ProtocoloResponse.model_validate(protocolo) if protocolo else None,
        minimo_integrantes=hackathon.min_integrantes,
        maximo_integrantes=hackathon.max_integrantes,
        total_integrantes=avaliacao.total,
        inscricoes_abertas=avaliacao.inscricoes_abertas,
        voce_e_lider=voce_e_lider,
        pode_concluir=(
            voce_e_lider
            and equipe.situacao == SituacaoEquipe.EM_FORMACAO
            and avaliacao.pode_concluir
        ),
        integrantes=integrantes,
        pendencias=[
            PendenciaResponse(
                codigo=p.codigo,
                mensagem=p.mensagem,
                usuario_id=p.usuario_id,
                bloqueia_conclusao=p.bloqueia_conclusao,
            )
            for p in avaliacao.pendencias
        ],
    )


async def concluir(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID
) -> ConclusaoInscricaoResponse:
    """O líder oficializa a participação da equipe (RF22).

    Exige inscrições abertas (RN06), 3 a 5 integrantes com convite e termos aceitos (RN01,
    RN05) e conta ativa. Convites ainda sem resposta são cancelados, já que a composição da
    equipe fecha aqui. Emite o protocolo e, se o vínculo de todos já estiver aprovado, a
    equipe é homologada na mesma operação (RF23).
    """
    equipe, hackathon = await _equipe_e_hackathon(db, equipe_id, para_atualizar=True)
    if not await _eh_lider(db, usuario, equipe.id):
        apenas_lider_da_equipe()
    if equipe.situacao != SituacaoEquipe.EM_FORMACAO:
        inscricao_ja_concluida()
    if not inscricoes_abertas(hackathon):
        fora_do_periodo_de_inscricao()

    avaliacao = await avaliar(db, equipe, hackathon)
    if not avaliacao.pode_concluir:
        requisitos_nao_cumpridos([p.mensagem for p in avaliacao.pendencias if p.bloqueia_conclusao])

    agora = datetime.now(UTC)
    try:
        await cancelar_convites_pendentes(db, equipe.id)
        equipe.situacao = SituacaoEquipe.AGUARDANDO_HOMOLOGACAO
        equipe.inscricao_concluida_em = agora
        equipe.atualizado_em = agora
        db.add(equipe)
        protocolo = await criar_protocolo(
            db,
            Protocolo(
                tipo=TipoProtocolo.INSCRICAO_EQUIPE, equipe_id=equipe.id, emitido_por=usuario.id
            ),
        )
        await reavaliar_homologacao(db, equipe, hackathon)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(equipe)

    if equipe.situacao == SituacaoEquipe.HOMOLOGADA:
        mensagem = (
            f"Inscrição concluída e equipe homologada. Protocolo {protocolo.numero}. "
            "Guarde o número como comprovante."
        )
    else:
        mensagem = (
            f"Inscrição concluída. Protocolo {protocolo.numero}. A equipe será homologada "
            "assim que o comprovante de vínculo de todos os integrantes for aprovado."
        )
    return ConclusaoInscricaoResponse(
        mensagem=mensagem,
        equipe_id=equipe.id,
        situacao=equipe.situacao,
        inscricao_concluida_em=equipe.inscricao_concluida_em,
        homologada_em=equipe.homologada_em,
        protocolo=ProtocoloResponse.model_validate(protocolo),
    )


async def reavaliar_equipe_do_usuario(
    db: AsyncSession, hackathon_id: UUID, usuario_id: UUID
) -> None:
    """Reavalia a homologação da equipe em que a pessoa está neste hackathon, se houver. Sem
    commit. Chamado quando o comprovante de alguém muda (RF21, RF23)."""
    membro = await get_membro_no_hackathon(db, hackathon_id, usuario_id)
    if membro is None:
        return
    equipe, hackathon = await _equipe_e_hackathon(db, membro.equipe_id, para_atualizar=True)
    await reavaliar_homologacao(db, equipe, hackathon)


async def reavaliar_hackathon(db: AsyncSession, hackathon_id: UUID) -> ReavaliacaoResponse:
    """Refaz a homologação de todas as equipes com inscrição concluída (RF23).

    Serve quando algo muda fora do fluxo de uma equipe, como a publicação de uma nova versão
    dos termos ou o ajuste do tamanho de equipe, e equipes homologadas deixam de cumprir os
    requisitos (ou passam a cumpri-los)."""
    hackathon = await get_hackathon_by_id(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()

    equipes = await listar_equipes_para_homologacao(db, hackathon_id)
    homologadas = revertidas = 0
    try:
        for equipe in equipes:
            antes = equipe.situacao
            depois = await reavaliar_homologacao(db, equipe, hackathon)
            homologadas += antes != depois and depois == SituacaoEquipe.HOMOLOGADA
            revertidas += antes != depois and depois == SituacaoEquipe.AGUARDANDO_HOMOLOGACAO
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return ReavaliacaoResponse(
        avaliadas=len(equipes), homologadas=homologadas, revertidas=revertidas
    )
