"""Quais eventos do sistema geram notificação in-app (BE-S5-04) e com que conteúdo.

Espelha `email_eventos`: cada função é chamada ao lado do aviso por e-mail, dentro da transação
do evento e sem commit, e usa as mesmas chaves de idempotência. O e-mail não é tocado aqui.
Um aviso que não pôde ser gravado não derruba a ação principal (veja `notificar`).
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FuncaoMembro, StatusConvite, TipoNotificacao
from app.controllers.membro_equipe import listar_membros
from app.models import Convite, Equipe, Protocolo, Submissao, Usuario
from app.services.notificacao import notificar


def _nome_equipe(equipe: Equipe) -> str:
    return equipe.nome or str(equipe.id)


async def _integrantes(db: AsyncSession, equipe: Equipe):
    return [m.usuario_id for m in await listar_membros(db, equipe.id)]


async def notificar_convite(
    db: AsyncSession, convite: Convite, equipe: Equipe, lider: Usuario
) -> None:
    """RF19: o convidado vê o convite na plataforma, se já tem conta. Sem conta, só o e-mail
    avisa; a notificação não é retroativa quando a conta é criada depois."""
    if convite.usuario_id is None:
        return
    await notificar(
        db,
        [convite.usuario_id],
        TipoNotificacao.CONVITE,
        "Convite para uma equipe",
        f"{lider.nome or 'O líder'} convidou você para a equipe {_nome_equipe(equipe)}.",
        chave=f"convite:{convite.id}",
        referencia_tipo="CONVITE",
        referencia_id=convite.id,
        dados={"convite_id": convite.id, "equipe_id": equipe.id},
    )


async def notificar_resposta_convite(
    db: AsyncSession, convite: Convite, equipe: Equipe, convidado: Usuario
) -> None:
    """RF19: o líder que convidou é avisado do aceite ou da recusa."""
    aceito = convite.status == StatusConvite.ACEITO
    resposta = "aceitou" if aceito else "recusou"
    await notificar(
        db,
        [convite.convidado_por],
        TipoNotificacao.ACEITE,
        "Resposta a um convite",
        f"{convite.nome or convidado.nome or convite.email} {resposta} o convite para a "
        f"equipe {_nome_equipe(equipe)}.",
        chave=f"convite-resposta:{convite.id}:{convite.status}",
        referencia_tipo="CONVITE",
        referencia_id=convite.id,
        dados={
            "convite_id": convite.id,
            "equipe_id": equipe.id,
            "resposta": "ACEITO" if aceito else "RECUSADO",
        },
    )


async def notificar_inscricao_concluida(
    db: AsyncSession, equipe: Equipe, protocolo: Protocolo
) -> None:
    """RF22: todos os integrantes recebem o protocolo da inscrição."""
    await notificar(
        db,
        await _integrantes(db, equipe),
        TipoNotificacao.INSCRICAO,
        "Inscrição concluída",
        f"A inscrição da equipe {_nome_equipe(equipe)} foi concluída. "
        f"Protocolo {protocolo.numero}.",
        chave=f"inscricao:{protocolo.id}",
        referencia_tipo="PROTOCOLO",
        referencia_id=protocolo.id,
        dados={"equipe_id": equipe.id, "protocolo_numero": protocolo.numero, "evento": "CONCLUIDA"},
    )


async def notificar_equipe_homologada(db: AsyncSession, equipe: Equipe) -> None:
    """RF23: a equipe é avisada quando passa a homologada. Se a homologação cair e voltar, cada
    vez é um fato novo (a chave inclui o momento), como no e-mail."""
    await notificar(
        db,
        await _integrantes(db, equipe),
        TipoNotificacao.INSCRICAO,
        "Equipe homologada",
        f"A equipe {_nome_equipe(equipe)} foi homologada.",
        chave=f"equipe_homologada:{equipe.id}:{equipe.homologada_em.isoformat()}",
        referencia_tipo="EQUIPE",
        referencia_id=equipe.id,
        dados={"equipe_id": equipe.id, "evento": "HOMOLOGADA"},
    )


async def notificar_protocolo_proposta(
    db: AsyncSession, equipe: Equipe, proposta: Submissao, protocolo: Protocolo
) -> None:
    """RF28: o líder recebe o protocolo do envio da proposta."""
    lideres = [
        m.usuario_id for m in await listar_membros(db, equipe.id) if m.funcao == FuncaoMembro.LIDER
    ]
    await notificar(
        db,
        lideres,
        TipoNotificacao.PROPOSTA,
        "Proposta enviada",
        f"A proposta da equipe {_nome_equipe(equipe)} foi enviada. Protocolo {protocolo.numero}.",
        chave=f"protocolo_proposta:{protocolo.id}",
        referencia_tipo="PROTOCOLO",
        referencia_id=protocolo.id,
        dados={
            "equipe_id": equipe.id,
            "submissao_id": proposta.id,
            "protocolo_numero": protocolo.numero,
        },
    )
