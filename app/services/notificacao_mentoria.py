"""RF60: outbox do PR #15 e eventos duráveis para a central in-app ainda não integrada."""

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoEmail
from app.controllers.membro_equipe import listar_membros_com_usuario
from app.models import AtribuicaoMentor, Equipe, EventoNotificacaoMentoria, Usuario
from app.services.email import enfileirar, link_front

ACOES = {
    "ATRIBUIDA": "atribuída",
    "SUBSTITUIDA": "atualizada por substituição",
    "ENCERRADA": "encerrada",
}


async def registrar(
    db: AsyncSession,
    atribuicao: AtribuicaoMentor,
    equipe: Equipe,
    tipo: str,
    mentor_anterior: Usuario | None = None,
) -> None:
    destinatarios = {
        usuario.id: usuario for _, usuario in await listar_membros_com_usuario(db, equipe.id)
    }
    mentor = await db.get(Usuario, atribuicao.mentor_id)
    destinatarios[mentor.id] = mentor
    if mentor_anterior is not None:
        destinatarios[mentor_anterior.id] = mentor_anterior
    for usuario in destinatarios.values():
        evento = EventoNotificacaoMentoria(
            atribuicao_id=atribuicao.id,
            usuario_id=usuario.id,
            tipo=tipo,
            mensagem=f"A mentoria da equipe {equipe.nome or equipe.id} foi {ACOES[tipo]}.",
        )
        db.add(evento)
        await db.flush()
        evento.email_enfileirado = await enfileirar(
            db,
            TipoEmail.ATRIBUICAO_MENTOR,
            usuario_id=usuario.id,
            destinatario_email=usuario.email,
            destinatario_nome=usuario.nome,
            contexto={
                "nome": usuario.nome or "participante",
                "equipe_nome": equipe.nome or str(equipe.id),
                "acao": ACOES[tipo],
                "link": link_front("/mentorias"),
            },
            chave=f"mentoria:{atribuicao.id}:{tipo}:{usuario.id}",
        )
        db.add(evento)
