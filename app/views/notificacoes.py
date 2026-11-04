from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.notificacao import NotificacaoResultadoResponse
from app.security.dependencias import usuario_ativo
from app.services.notificacao import listar_minhas
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/me/notificacoes", tags=["Notificações"])


@router.get(
    "",
    response_model=list[NotificacaoResultadoResponse],
    summary="Listar minhas notificações",
    description=(
        "RF33. Notificações do resultado do usuário autenticado, da mais recente para a mais "
        "antiga. Cada uma informa se a proposta da equipe foi aprovada, a mensagem, o parecer "
        "(anônimo) e o canal com o `status_envio` (PENDENTE, ENVIADO ou FALHA, com `erro`). "
        "Hoje só existe o canal PLATAFORMA; o e-mail depende da decisão Q16. Não há rota para "
        "marcar como lida."
    ),
    responses=respostas_de_erro(
        {401: "Sem token, ou token inválido, vencido ou de conta desativada", 403: "Conta pendente"}
    ),
)
async def minhas_notificacoes(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_ativo)
):
    return await listar_minhas(db, usuario.id)
