"""Reenvio seguro e correção de convite pendente (BE-S5-06; RF01, RF18, RF19, RF20, RF60).

O líder reenvia um convite que ainda não foi respondido (inclusive com o link vencido) ou corrige
o nome e o e-mail dele. Os dois caminhos renovam o aviso do mesmo jeito:

- o convite é travado (`FOR UPDATE`) e, depois, a equipe, a mesma ordem do aceite; reenvios e
  correções simultâneos se enfileiram e sobra um único token válido;
- quem não tem conta recebe um token novo: o banco guarda só o hash, o link anterior deixa de
  existir (cai no mesmo 400 dos links inválidos) e o valor puro só vai no e-mail;
- quem já tem conta recebe a notificação na central e o e-mail que leva a `/convites`;
- o aviso anterior que ainda estava na fila é retirado, e cada envio usa a sua chave de
  idempotência (`convite:{id}:envio:{n}`), senão a fila o trataria como repetido.

O reenvio simples respeita o intervalo mínimo e o máximo por convite. A troca de e-mail conta no
máximo, mas não no intervalo, para o líder corrigir um endereço digitado errado na hora.
"""

import secrets
from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import PapelUsuario, StatusConvite
from app.controllers.convite import contar_pendentes, get_convite_by_id, salvar_convite
from app.controllers.email_outbox import cancelar_aviso_pendente
from app.controllers.membro_equipe import contar_membros, get_membro
from app.controllers.notificacao import marcar_do_convite_como_lidas
from app.controllers.usuario import get_usuario_by_email
from app.exceptions.convite import (
    convite_ja_respondido,
    convite_nao_encontrado,
    equipe_sem_vagas,
    ja_e_integrante,
    limite_de_reenvios,
    reenvio_muito_cedo,
)
from app.models import Convite, Equipe, Hackathon, Usuario
from app.schemas.convite import ConviteCorrecao
from app.services.convite import (
    equipe_e_hackathon,
    exigir_equipe_em_formacao,
    exigir_inscricoes_abertas,
    exigir_lider,
)
from app.services.email_eventos import avisar_convite
from app.services.notificacao_eventos import notificar_convite
from app.services.somente_leitura import exigir_equipe_editavel
from app.services.token_usuario import hash_do_token
from app.utils.convite import chave_do_envio
from app.validations.inscricao import como_utc


def _agora_utc() -> datetime:
    return datetime.now(UTC)


async def _convite_do_lider(
    db: AsyncSession, lider: Usuario, convite_id: UUID
) -> tuple[Convite, Equipe, Hackathon]:
    """Trava o convite e a equipe e confere quem pede. Para quem não é da equipe o convite 'não
    existe' (404, como no restante do projeto); integrante que não lidera recebe 403. Só vale
    para convite pendente, com as inscrições abertas e a equipe ainda em formação."""
    convite = await get_convite_by_id(db, convite_id, para_atualizar=True)
    if convite is None:
        convite_nao_encontrado()
    if lider.papel != PapelUsuario.DEV:
        if await get_membro(db, convite.equipe_id, lider.id) is None:
            convite_nao_encontrado()
    await exigir_lider(db, convite.equipe_id, lider)
    equipe, hackathon = await equipe_e_hackathon(db, convite.equipe_id, para_atualizar=True)
    await exigir_equipe_editavel(db, equipe.id)
    if convite.status != StatusConvite.PENDENTE:
        convite_ja_respondido()
    exigir_inscricoes_abertas(hackathon)
    exigir_equipe_em_formacao(equipe)
    return convite, equipe, hackathon


def _exigir_intervalo(convite: Convite, agora: datetime) -> None:
    liberado_em = como_utc(convite.ultimo_envio_em) + timedelta(
        seconds=settings.CONVITE_REENVIO_INTERVALO_SEGUNDOS
    )
    if agora < liberado_em:
        reenvio_muito_cedo(ceil((liberado_em - agora).total_seconds()))


async def _renovar_aviso(
    db: AsyncSession, convite: Convite, equipe: Equipe, *, respeitar_intervalo: bool
) -> None:
    """Gera o aviso novo do convite, para o e-mail que ele tem agora. Sem commit; quem chama já
    travou o convite e a equipe e validou as regras da equipe."""
    if convite.reenvios >= settings.CONVITE_REENVIO_MAX:
        limite_de_reenvios(settings.CONVITE_REENVIO_MAX)
    agora = _agora_utc()
    if respeitar_intervalo:
        _exigir_intervalo(convite, agora)

    chave_anterior = chave_do_envio(convite.id, convite.reenvios)
    conta = await get_usuario_by_email(db, convite.email)
    convite.usuario_id = conta.id if conta else None
    token = None
    if conta is None:
        # Sem conta: link de cadastro novo, de uso único. O hash substitui o anterior, que
        # deixa de existir; o valor puro só vai ao e-mail
        token = secrets.token_urlsafe(32)
        convite.token_hash = hash_do_token(token)
        convite.token_expira_em = agora + timedelta(minutes=settings.CONVITE_CADASTRO_MINUTOS)
        convite.token_utilizado_em = None
    else:
        # Com conta o convite é respondido logado: o link de cadastro anterior não vale mais
        convite.token_hash = None
        convite.token_expira_em = None
    convite.reenvios += 1
    convite.ultimo_envio_em = agora
    await salvar_convite(db, convite)

    await cancelar_aviso_pendente(db, chave_anterior)
    lider = await db.get(Usuario, convite.convidado_por)
    await avisar_convite(db, convite, equipe, lider, token)
    await notificar_convite(db, convite, equipe, lider)


async def reenviar_convite(db: AsyncSession, lider: Usuario, convite_id: UUID) -> Convite:
    """O líder reenvia um convite pendente ao mesmo e-mail, com intervalo mínimo e máximo de
    reenvios por convite."""
    convite, equipe, _ = await _convite_do_lider(db, lider, convite_id)
    await _renovar_aviso(db, convite, equipe, respeitar_intervalo=True)
    await db.commit()
    await db.refresh(convite)
    return convite


async def corrigir_convite(
    db: AsyncSession, lider: Usuario, convite_id: UUID, dados: ConviteCorrecao
) -> Convite:
    """O líder corrige o nome e/ou o e-mail de um convite pendente. Só o nome não gera aviso e
    não conta nos limites. Trocar o e-mail revalida as regras da equipe, invalida o link do
    endereço antigo e envia um novo ao corrigido. Não mexe em nenhuma conta (`usuarios`)."""
    convite, equipe, hackathon = await _convite_do_lider(db, lider, convite_id)

    if dados.nome is not None:
        convite.nome = dados.nome
    novo_email = str(dados.email).lower() if dados.email is not None else None
    if novo_email is None or novo_email == convite.email.lower():
        db.add(convite)
        await db.commit()
        await db.refresh(convite)
        return convite

    conta = await get_usuario_by_email(db, novo_email)
    if conta is not None and await get_membro(db, equipe.id, conta.id) is not None:
        ja_e_integrante()
    # O convite corrigido já conta entre os pendentes: só barra se a equipe estourou o máximo
    ocupadas = await contar_membros(db, equipe.id) + await contar_pendentes(db, equipe.id)
    if ocupadas > hackathon.max_integrantes:
        equipe_sem_vagas(hackathon.max_integrantes)

    antiga = convite.usuario_id
    convite.email = novo_email
    # Grava já: o e-mail que a equipe já convidou vira 409 aqui, e não num autoflush adiante
    await salvar_convite(db, convite)
    await _renovar_aviso(db, convite, equipe, respeitar_intervalo=False)
    if antiga is not None and antiga != convite.usuario_id:
        # O convite deixou de ser dela: o aviso que a conta antiga recebeu sai da fila de não lidas
        await marcar_do_convite_como_lidas(db, antiga, convite.id)
    await db.commit()
    await db.refresh(convite)
    return convite
