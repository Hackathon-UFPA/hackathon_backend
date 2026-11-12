"""Quais eventos do sistema geram e-mail (RF60, RN32) e com que conteúdo.

Cada função grava os e-mails na fila, sem commit, dentro da transação do evento. A chave de
idempotência impede avisar duas vezes pelo mesmo fato. Mensagens de chat nunca geram e-mail
(RN32), e o e-mail traz só o aviso e o link para a plataforma (RNF28).
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FuncaoMembro, TipoEmail
from app.controllers.membro_equipe import listar_membros_com_usuario
from app.models import Convite, Equipe, Protocolo, ResultadoProposta, Submissao, Usuario
from app.services.email import enfileirar, link_front


def _nome(usuario: Usuario) -> str:
    return usuario.nome or "participante"


async def avisar_convite(
    db: AsyncSession, convite: Convite, equipe: Equipe, lider: Usuario
) -> None:
    """RF18, RF19: o convidado recebe o aviso do convite, tenha ou não conta."""
    await enfileirar(
        db,
        TipoEmail.CONVITE_EQUIPE,
        destinatario_email=convite.email,
        destinatario_nome=convite.nome,
        usuario_id=convite.usuario_id,
        contexto={
            "nome": convite.nome,
            "equipe_nome": equipe.nome,
            "lider_nome": lider.nome,
            "link": link_front("/convites"),
        },
        chave=f"convite:{convite.id}",
    )


async def avisar_inscricao_concluida(
    db: AsyncSession, equipe: Equipe, protocolo: Protocolo
) -> None:
    """RF22: todos os integrantes recebem o protocolo da inscrição."""
    for _, usuario in await listar_membros_com_usuario(db, equipe.id):
        await enfileirar(
            db,
            TipoEmail.INSCRICAO_CONCLUIDA,
            destinatario_email=usuario.email,
            destinatario_nome=usuario.nome,
            usuario_id=usuario.id,
            contexto={
                "nome": _nome(usuario),
                "equipe_nome": equipe.nome,
                "protocolo_numero": protocolo.numero,
                "link": link_front(f"/equipes/{equipe.id}"),
            },
            chave=f"inscricao:{protocolo.id}:{usuario.id}",
        )


async def avisar_equipe_homologada(db: AsyncSession, equipe: Equipe) -> None:
    """RF23, RF60: a equipe é avisada quando passa a homologada. Se a homologação cair e
    voltar, cada vez conta como um fato novo (a chave inclui o momento)."""
    for _, usuario in await listar_membros_com_usuario(db, equipe.id):
        await enfileirar(
            db,
            TipoEmail.EQUIPE_HOMOLOGADA,
            destinatario_email=usuario.email,
            destinatario_nome=usuario.nome,
            usuario_id=usuario.id,
            contexto={
                "nome": _nome(usuario),
                "equipe_nome": equipe.nome,
                "link": link_front(f"/equipes/{equipe.id}"),
            },
            chave=f"equipe_homologada:{equipe.id}:{usuario.id}:{equipe.homologada_em.isoformat()}",
        )


async def avisar_protocolo_proposta(
    db: AsyncSession, equipe: Equipe, proposta: Submissao, protocolo: Protocolo
) -> None:
    """RF28: o líder recebe o protocolo do envio da proposta."""
    for membro, usuario in await listar_membros_com_usuario(db, equipe.id):
        if membro.funcao != FuncaoMembro.LIDER:
            continue
        await enfileirar(
            db,
            TipoEmail.PROTOCOLO_PROPOSTA,
            destinatario_email=usuario.email,
            destinatario_nome=usuario.nome,
            usuario_id=usuario.id,
            contexto={
                "nome": _nome(usuario),
                "equipe_nome": equipe.nome,
                "protocolo_numero": protocolo.numero,
                "enviado_em": proposta.enviado_em,
                "link": link_front(f"/equipes/{equipe.id}"),
            },
            chave=f"protocolo_proposta:{protocolo.id}:{usuario.id}",
        )


async def avisar_resultado(db: AsyncSession, resultados: list[ResultadoProposta]) -> None:
    """RF33: todos os integrantes de cada equipe com proposta no resultado, aprovada ou não.
    O e-mail diz só se foi aprovada: o parecer fica na plataforma (RNF28)."""
    for resultado in resultados:
        for _, usuario in await listar_membros_com_usuario(db, resultado.equipe_id):
            await enfileirar(
                db,
                TipoEmail.RESULTADO_PROPOSTA,
                destinatario_email=usuario.email,
                destinatario_nome=usuario.nome,
                usuario_id=usuario.id,
                contexto={
                    "nome": _nome(usuario),
                    "equipe_nome": resultado.equipe_nome,
                    "aprovada": resultado.aprovada,
                    "link": link_front(f"/equipes/{resultado.equipe_id}/resultado"),
                },
                chave=f"resultado:{resultado.homologacao_id}:{resultado.equipe_id}:{usuario.id}",
            )
