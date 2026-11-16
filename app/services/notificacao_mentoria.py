"""RF60: cada evento de mentoria vira um registro durável (`eventos_notificacao_mentoria`), um
e-mail na fila (BE-S5-05) e uma notificação na central in-app (BE-S5-04)."""

from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoEmail, TipoNotificacao
from app.controllers.membro_equipe import listar_membros_com_usuario
from app.models import AtribuicaoMentor, Equipe, EventoNotificacaoMentoria, Usuario
from app.services.email import enfileirar, link_front
from app.services.notificacao import notificar

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
    eventos = []
    for usuario in destinatarios.values():
        evento = EventoNotificacaoMentoria(
            atribuicao_id=atribuicao.id,
            usuario_id=usuario.id,
            tipo=tipo,
            mensagem=f"A mentoria da equipe {equipe.nome or equipe.id} foi {ACOES[tipo]}.",
        )
        db.add(evento)
        eventos.append(evento)
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
    # Central in-app: mesma mensagem do evento, uma notificação por destinatário. Se não for
    # possível gravar, o evento fica com `publicado_na_plataforma_em` nulo (pendente).
    publicadas = await notificar(
        db,
        list(destinatarios),
        TipoNotificacao.MENTOR,
        "Mentoria da equipe",
        f"A mentoria da equipe {equipe.nome or equipe.id} foi {ACOES[tipo]}.",
        chave=f"mentoria:{atribuicao.id}:{tipo}",
        referencia_tipo="ATRIBUICAO_MENTOR",
        referencia_id=atribuicao.id,
        dados={"atribuicao_id": atribuicao.id, "equipe_id": equipe.id, "evento": tipo},
    )
    if publicadas is not None:
        agora = datetime.now(UTC)
        for evento in eventos:
            evento.publicado_na_plataforma_em = agora
            db.add(evento)
