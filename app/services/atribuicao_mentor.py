from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon
from app.controllers import atribuicao_mentor as controller
from app.controllers.equipe import get_equipe_by_id, get_hackathon_by_id
from app.controllers.hackathon import get_hackathon_para_atualizar
from app.controllers.resultado import get_homologacao
from app.exceptions.atribuicao_mentor import atribuicao_nao_encontrada, conflito_mentoria
from app.exceptions.convite import equipe_nao_encontrada, hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.models import AtribuicaoMentor, Hackathon, Usuario
from app.schemas.atribuicao_mentor import (
    AtribuicaoCreate,
    AtribuicaoEncerrar,
    EquipeAcompanhadaResponse,
    MentorContato,
    MentorDaEquipeResponse,
)
from app.services.equipe import consultar as consultar_equipe_do_usuario
from app.services.mentor import consultar as consultar_mentor
from app.services.mentor import validar_elegibilidade
from app.services.notificacao_mentoria import registrar as notificar


def _edicao_aberta(hackathon: Hackathon) -> None:
    if hackathon.status in (StatusHackathon.FINALIZADO, StatusHackathon.CANCELADO):
        conflito_mentoria("A edição está finalizada ou cancelada.")


async def treinamento(db: AsyncSession, hackathon_id: UUID) -> Hackathon:
    hackathon = await get_hackathon_by_id(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    return hackathon


async def concluir_treinamento(db: AsyncSession, usuario: Usuario, hackathon_id: UUID) -> Hackathon:
    hackathon = await get_hackathon_para_atualizar(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    _edicao_aberta(hackathon)
    if await get_homologacao(db, hackathon_id) is None:
        conflito_mentoria("Homologue o resultado antes de concluir o treinamento.")
    if hackathon.treinamento_concluido_em is None:
        hackathon.treinamento_concluido_em = datetime.now(UTC)
        hackathon.treinamento_concluido_por = usuario.id
        db.add(hackathon)
    await db.commit()
    return hackathon


async def atribuir(
    db: AsyncSession,
    usuario: Usuario,
    equipe_id: UUID,
    dados: AtribuicaoCreate,
    *,
    atribuicao_atual_id: UUID | None = None,
) -> AtribuicaoMentor:
    try:
        equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=True)
        if equipe is None:
            equipe_nao_encontrada()
        hackathon = await treinamento(db, equipe.hackathon_id)
        _edicao_aberta(hackathon)
        if hackathon.treinamento_concluido_em is None:
            conflito_mentoria("A atribuição só é permitida após a conclusão do treinamento.")
        if not await controller.equipe_aprovada(db, equipe.id, equipe.hackathon_id):
            conflito_mentoria("A equipe não possui proposta aprovada em resultado homologado.")
        atual = await controller.vigente(db, equipe.id)
        if atribuicao_atual_id is None and atual is not None:
            conflito_mentoria("A equipe já possui mentor. Utilize a substituição.")
        if atribuicao_atual_id is not None and (atual is None or atual.id != atribuicao_atual_id):
            conflito_mentoria("A atribuição vigente mudou; consulte a equipe novamente.")
        if atual is not None and atual.mentor_id == dados.mentor_id:
            conflito_mentoria("Este mentor já acompanha a equipe.")
        ids = {dados.mentor_id} | ({atual.mentor_id} if atual else set())
        await controller.bloquear_mentores(db, ids)
        mentor = await validar_elegibilidade(db, dados.mentor_id, equipe.hackathon_id)
        if await controller.contar_vigentes(db, mentor.id) >= mentor.max_equipes:
            conflito_mentoria("A capacidade máxima de equipes deste mentor foi atingida.")
        anteriores = await controller.historico(db, equipe.id, 1, 0)
        anterior = anteriores[0] if anteriores else None
        # Sob a trava da equipe, o vínculo vigente é sempre o predecessor da substituição.
        if atual is not None:
            anterior = atual
        agora = datetime.now(UTC)
        mentor_anterior = None
        if atual is not None:
            mentor_anterior = await db.get(Usuario, atual.mentor_id)
            atual.encerrada_em = agora
            atual.encerrada_por = usuario.id
            atual.motivo_encerramento = dados.motivo
            await controller.salvar(db, atual)
        nova = AtribuicaoMentor(
            equipe_id=equipe.id,
            hackathon_id=equipe.hackathon_id,
            mentor_id=mentor.id,
            atribuido_por=usuario.id,
            atribuido_em=agora,
            motivo=dados.motivo,
            atribuicao_anterior_id=anterior.id if anterior else None,
        )
        await controller.salvar(db, nova)
        await notificar(db, nova, equipe, "SUBSTITUIDA" if atual else "ATRIBUIDA", mentor_anterior)
        await db.commit()
        return nova
    except IntegrityError as error:
        await db.rollback()
        if "uq_atribuicoes_" in str(error.orig):
            conflito_mentoria("A atribuição da equipe mudou em outra operação.")
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise


async def encerrar(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, dados: AtribuicaoEncerrar
) -> AtribuicaoMentor:
    try:
        equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=True)
        if equipe is None:
            equipe_nao_encontrada()
        atual = await controller.vigente(db, equipe.id)
        if atual is None or atual.id != dados.atribuicao_atual_id:
            conflito_mentoria("A atribuição vigente mudou; consulte a equipe novamente.")
        await controller.bloquear_mentores(db, {atual.mentor_id})
        atual.encerrada_em = datetime.now(UTC)
        atual.encerrada_por = usuario.id
        atual.motivo_encerramento = dados.motivo
        await controller.salvar(db, atual)
        await notificar(db, atual, equipe, "ENCERRADA")
        await db.commit()
        return atual
    except Exception:
        await db.rollback()
        raise


async def consultar_admin(db: AsyncSession, equipe_id: UUID) -> AtribuicaoMentor:
    if await get_equipe_by_id(db, equipe_id) is None:
        equipe_nao_encontrada()
    atual = await controller.vigente(db, equipe_id)
    if atual is None:
        atribuicao_nao_encontrada()
    return atual


async def historico(db: AsyncSession, equipe_id: UUID, limite: int, deslocamento: int):
    if await get_equipe_by_id(db, equipe_id) is None:
        equipe_nao_encontrada()
    return await controller.historico(db, equipe_id, limite, deslocamento)


async def mentor_da_equipe(db: AsyncSession, usuario: Usuario, equipe_id: UUID):
    equipe = await consultar_equipe_do_usuario(db, usuario, equipe_id)
    atual = await controller.vigente(db, equipe.id)
    if atual is None:
        atribuicao_nao_encontrada()
    mentor = await db.get(Usuario, atual.mentor_id)
    return MentorDaEquipeResponse(
        atribuicao_id=atual.id,
        equipe_id=equipe.id,
        hackathon_id=equipe.hackathon_id,
        atribuido_em=atual.atribuido_em,
        mentor=MentorContato.model_validate(mentor),
    )


async def equipes_do_mentor(
    db: AsyncSession,
    mentor_id: UUID,
    hackathon_id: UUID | None,
    apenas_vigentes: bool,
    limite: int,
    deslocamento: int,
) -> list[EquipeAcompanhadaResponse]:
    await consultar_mentor(db, mentor_id)
    return [
        EquipeAcompanhadaResponse(atribuicao=atribuicao, equipe_nome=nome)
        for atribuicao, nome in await controller.equipes_do_mentor(
            db, mentor_id, hackathon_id, apenas_vigentes, limite, deslocamento
        )
    ]
