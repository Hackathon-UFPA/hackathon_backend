"""Feedbacks do mentor (BE-S6-03, RF40) e histórico da mentoria (RF42).

Escrita: só o mentor com atribuição vigente na equipe (e DEV). Leitura: integrantes da equipe,
mentor vigente, gestores da organização dona da edição e DEV. Quem está fora do escopo recebe o
mesmo 404 de uma equipe inexistente.

Q24 (pendente): vale a regra restritiva. O mentor só lê as equipes que acompanha hoje, com todo o
histórico delas, inclusive os feedbacks de mentores anteriores."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, TipoNotificacao
from app.controllers import feedback_mentoria as controller
from app.controllers.atribuicao_mentor import vigente
from app.controllers.conteudo import get_item
from app.controllers.equipe import get_equipe_by_id
from app.controllers.membro_equipe import get_membro, listar_membros
from app.controllers.mentoria import get_entrega
from app.exceptions.atribuicao_mentor import conflito_mentoria
from app.exceptions.convite import equipe_nao_encontrada
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.feedback_mentoria import feedback_invalido
from app.models import Equipe, FeedbackMentoria, Hackathon, MarcoMentoria, Usuario
from app.schemas.feedback_mentoria import (
    FeedbackMentoriaCreate,
    FeedbackMentoriaResponse,
    ItemHistorico,
    ItemHistoricoEntrega,
    ItemHistoricoFeedback,
)
from app.schemas.mentoria import EntregaMentoriaResponse
from app.security.organizacao import mesma_organizacao
from app.services.atribuicao_mentor import exigir_edicao_nao_encerrada
from app.services.conteudo import agora_utc
from app.services.hackathon import obter_acessivel
from app.services.mentoria import GESTORES_MENTORIA, _equipe_autorizada
from app.services.notificacao import notificar

TITULO_NOTIFICACAO = "Novo feedback da mentoria"


def resposta(
    feedback: FeedbackMentoria, autor_nome: str | None, corrigido_por_id: UUID | None
) -> FeedbackMentoriaResponse:
    return FeedbackMentoriaResponse(
        id=feedback.id,
        equipe_id=feedback.equipe_id,
        hackathon_id=feedback.hackathon_id,
        marco_id=feedback.marco_id,
        entrega_id=feedback.entrega_id,
        autor_nome=autor_nome,
        status_acompanhamento=feedback.status_acompanhamento,
        texto=feedback.texto,
        criado_em=feedback.criado_em,
        corrige_id=feedback.corrige_id,
        corrigido_por_id=corrigido_por_id,
    )


async def _equipe_e_edicao(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, *, para_atualizar: bool = False
) -> tuple[Equipe, Hackathon]:
    equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=para_atualizar)
    if equipe is None:
        equipe_nao_encontrada()
    try:
        hackathon = await obter_acessivel(db, equipe.hackathon_id, usuario)
    except HTTPException:
        equipe_nao_encontrada()
    return equipe, hackathon


async def _autorizar_leitura(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> None:
    equipe, hackathon = await _equipe_e_edicao(db, usuario, equipe_id)
    if usuario.papel == PapelUsuario.DEV:
        return
    if usuario.papel in GESTORES_MENTORIA and mesma_organizacao(usuario, hackathon.organizacao_id):
        return
    if usuario.papel == PapelUsuario.MENTOR and mesma_organizacao(
        usuario, hackathon.organizacao_id
    ):
        atribuicao = await vigente(db, equipe.id)
        if atribuicao is not None and atribuicao.mentor_id == usuario.id:
            return
    if usuario.papel == PapelUsuario.PARTICIPANTE:
        if await get_membro(db, equipe.id, usuario.id) is not None:
            return
    equipe_nao_encontrada()


def _mesmo_pedido(feedback: FeedbackMentoria, equipe_id: UUID, dados: FeedbackMentoriaCreate):
    """Compara o pedido repetido com o feedback gravado. O marco derivado da entrega não precisa
    ser reenviado."""
    marco_igual = (
        dados.marco_id is None and dados.entrega_id is not None
    ) or dados.marco_id == feedback.marco_id
    return (
        feedback.equipe_id == equipe_id
        and feedback.texto == dados.texto
        and feedback.status_acompanhamento == dados.status_acompanhamento
        and feedback.entrega_id == dados.entrega_id
        and feedback.corrige_id == dados.corrige_id
        and marco_igual
    )


async def _repeticao(
    db: AsyncSession, autor_id: UUID, equipe_id: UUID, dados: FeedbackMentoriaCreate, chave: str
) -> FeedbackMentoriaResponse | None:
    linha = await controller.get_por_chave(db, autor_id, chave)
    if linha is None:
        return None
    if not _mesmo_pedido(linha[0], equipe_id, dados):
        conflito_mentoria("A Idempotency-Key já foi usada com outro conteúdo.")
    return resposta(*linha)


async def _vinculos(db: AsyncSession, equipe: Equipe, dados: FeedbackMentoriaCreate) -> UUID | None:
    """Devolve o marco do feedback. Marco e entrega precisam ser da edição e da equipe."""
    marco_id = dados.marco_id
    if dados.entrega_id is not None:
        entrega = await get_entrega(db, equipe.id, dados.entrega_id)
        if entrega is None:
            feedback_invalido("A entrega não existe nesta equipe.")
        if marco_id is not None and marco_id != entrega.marco_id:
            feedback_invalido("O marco informado não é o da entrega.")
        return entrega.marco_id
    if marco_id is not None:
        if await get_item(db, MarcoMentoria, equipe.hackathon_id, marco_id) is None:
            feedback_invalido("O marco não existe nesta edição.")
    return marco_id


async def _validar_correcao(
    db: AsyncSession, usuario: Usuario, equipe: Equipe, corrige_id: UUID
) -> None:
    linha = await controller.get_da_equipe(db, equipe.id, corrige_id)
    if linha is None:
        feedback_invalido("O feedback a corrigir não existe nesta equipe.")
    original, _, corrigido_por_id = linha
    if original.autor_id != usuario.id:
        feedback_invalido("Só o autor corrige o próprio feedback. Escreva um novo feedback.")
    if corrigido_por_id is not None:
        conflito_mentoria("Este feedback já foi corrigido.")


async def _notificar(db: AsyncSession, usuario: Usuario, feedback: FeedbackMentoria) -> None:
    """Só in-app (nunca e-mail) e sem o texto: ele fica na consulta, com as permissões dela."""
    integrantes = await listar_membros(db, feedback.equipe_id)
    await notificar(
        db,
        [m.usuario_id for m in integrantes if m.usuario_id != usuario.id],
        TipoNotificacao.MENTOR,
        TITULO_NOTIFICACAO,
        "A equipe recebeu um novo feedback do mentor. "
        f"Consulte em GET /equipes/{feedback.equipe_id}/mentoria/feedbacks.",
        chave=f"feedback_mentoria:{feedback.id}",
        referencia_tipo="FEEDBACK_MENTORIA",
        referencia_id=feedback.id,
        dados={
            "equipe_id": feedback.equipe_id,
            "status_acompanhamento": feedback.status_acompanhamento,
        },
    )


async def registrar(
    db: AsyncSession,
    usuario: Usuario,
    equipe_id: UUID,
    dados: FeedbackMentoriaCreate,
    chave: str | None,
) -> tuple[FeedbackMentoriaResponse, bool]:
    """Devolve o feedback e se ele foi criado agora (False numa repetição da mesma chave)."""
    equipe, hackathon = await _equipe_e_edicao(db, usuario, equipe_id)
    atribuicao = await controller.vigente_travada(db, equipe.id)
    if usuario.papel == PapelUsuario.MENTOR and (
        not mesma_organizacao(usuario, hackathon.organizacao_id)
        or atribuicao is None
        or atribuicao.mentor_id != usuario.id
    ):
        equipe_nao_encontrada()
    if chave is not None and (
        repetido := await _repeticao(db, usuario.id, equipe.id, dados, chave)
    ):
        return repetido, False
    if atribuicao is None:
        conflito_mentoria("A equipe não tem mentor com atribuição vigente.")
    exigir_edicao_nao_encerrada(hackathon)
    if not await _equipe_autorizada(db, equipe):
        conflito_mentoria("A equipe precisa estar homologada e ter proposta aprovada.")
    marco_id = await _vinculos(db, equipe, dados)
    if dados.corrige_id is not None:
        await _validar_correcao(db, usuario, equipe, dados.corrige_id)

    feedback = FeedbackMentoria(
        equipe_id=equipe.id,
        hackathon_id=equipe.hackathon_id,
        atribuicao_id=atribuicao.id,
        autor_id=usuario.id,
        marco_id=marco_id,
        entrega_id=dados.entrega_id,
        status_acompanhamento=dados.status_acompanhamento,
        texto=dados.texto,
        corrige_id=dados.corrige_id,
        criado_em=agora_utc(),
        chave_idempotencia=chave,
    )
    # O rollback expira os objetos da sessão: guardar o que a resposta ainda precisa.
    nome, autor_id = usuario.nome, usuario.id
    try:
        db.add(feedback)
        await _notificar(db, usuario, feedback)
        await db.commit()
    except IntegrityError as erro:
        await db.rollback()
        if feedback in db:  # senão a próxima consulta tenta gravá-lo de novo (autoflush)
            db.expunge(feedback)
        mensagem = str(erro.orig)
        if "uq_feedbacks_mentoria_corrige" in mensagem:
            conflito_mentoria("Este feedback já foi corrigido.")
        if "uq_feedbacks_mentoria_autor_chave" in mensagem and chave is not None:
            # Pedido simultâneo com a mesma chave: o outro venceu, devolve o dele.
            repetido = await _repeticao(db, autor_id, equipe_id, dados, chave)
            if repetido is not None:
                return repetido, False
        erro_de_integridade_sql(erro)
    return resposta(feedback, nome, None), True


async def listar(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, limite: int, deslocamento: int
) -> list[FeedbackMentoriaResponse]:
    await _autorizar_leitura(db, usuario, equipe_id)
    linhas = await controller.listar(db, equipe_id, limite, deslocamento)
    return [resposta(*linha) for linha in linhas]


async def historico(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, limite: int, deslocamento: int
) -> list[ItemHistorico]:
    await _autorizar_leitura(db, usuario, equipe_id)
    posicoes = await controller.historico(db, equipe_id, limite, deslocamento)
    ids_entregas = [id_ for tipo, id_ in posicoes if tipo == "ENTREGA"]
    ids_feedbacks = [id_ for tipo, id_ in posicoes if tipo == "FEEDBACK"]
    entregas = await controller.entregas_por_id(db, ids_entregas) if ids_entregas else {}
    feedbacks = await controller.feedbacks_por_id(db, ids_feedbacks) if ids_feedbacks else {}
    itens: list[ItemHistorico] = []
    for tipo, id_ in posicoes:
        if tipo == "ENTREGA":
            entrega = entregas[id_]
            itens.append(
                ItemHistoricoEntrega(
                    ocorrido_em=entrega.enviado_em,
                    entrega=EntregaMentoriaResponse.model_validate(entrega),
                )
            )
        else:
            linha = feedbacks[id_]
            itens.append(
                ItemHistoricoFeedback(ocorrido_em=linha[0].criado_em, feedback=resposta(*linha))
            )
    return itens
