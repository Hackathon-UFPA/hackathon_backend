from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoNotificacao
from app.db.db import get_session
from app.models import Usuario
from app.schemas.notificacao import (
    ContagemNaoLidasResponse,
    MarcadasComoLidasResponse,
    NotificacaoResponse,
)
from app.security.dependencias import usuario_ativo
from app.services.notificacao import (
    contar_nao_lidas,
    listar_minhas,
    marcar_lida,
    marcar_todas_lidas,
)
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/me/notificacoes", tags=["Notificações"])

ERROS_AUTENTICACAO = {
    401: "Sem token, ou token inválido, vencido ou de conta desativada",
    403: "Conta pendente",
}


@router.get(
    "",
    response_model=list[NotificacaoResponse],
    summary="Listar minhas notificações",
    description=(
        "Central de notificações do usuário autenticado (RF19, RF22, RF28, RF33, RF38, RF53, "
        "RF60, RF61), da mais recente para a mais antiga. Só o próprio usuário as vê (DEV "
        "também). Cada item traz `tipo` (CONVITE, ACEITE, INSCRICAO, PROPOSTA, RESULTADO, "
        "MENTOR, CHAT ou PRAZO), `titulo`, `mensagem`, `dados`, `referencia`, `criado_em` e "
        "`lida_em` (nulo se não lida). O item RESULTADO (RF33) mantém os campos de antes: "
        "`id`, `aprovada`, `canal`, `status_envio`, `erro` e `pareceres`. Todo item traz "
        "`notificacao_id`, o id a usar nas rotas de leitura (única mudança aditiva do "
        "contrato). Filtros: `lida` e `tipo`. Paginação por `limite` (1 a 100, padrão 100) e "
        "`deslocamento`; o cabeçalho `X-Total-Count` traz o total que o filtro alcança. "
        "O e-mail dos eventos segue por `/admin/emails`; mensagens de chat só existem aqui."
    ),
    responses=respostas_de_erro(ERROS_AUTENTICACAO),
)
async def minhas_notificacoes(
    response: Response,
    lida: bool | None = Query(
        default=None, description="true só as lidas; false só as não lidas; omitido, todas"
    ),
    tipo: TipoNotificacao | None = Query(default=None, description="Filtra pelo tipo"),
    limite: int = Query(default=100, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    itens, total = await listar_minhas(
        db, usuario.id, lida=lida, tipo=tipo, limite=limite, deslocamento=deslocamento
    )
    response.headers["X-Total-Count"] = str(total)
    return itens


@router.get(
    "/nao-lidas/contagem",
    response_model=ContagemNaoLidasResponse,
    summary="Contar minhas notificações não lidas",
    description="Quantas notificações do usuário autenticado ainda não foram lidas.",
    responses=respostas_de_erro(ERROS_AUTENTICACAO),
)
async def contagem_nao_lidas(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_ativo)
):
    return ContagemNaoLidasResponse(nao_lidas=await contar_nao_lidas(db, usuario.id))


@router.post(
    "/lidas",
    response_model=MarcadasComoLidasResponse,
    summary="Marcar todas as minhas notificações como lidas",
    description=(
        "Marca como lidas as notificações ainda não lidas do usuário autenticado. Idempotente: "
        "repetir devolve `marcadas = 0`."
    ),
    responses=respostas_de_erro(ERROS_AUTENTICACAO),
)
async def marcar_todas(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_ativo)
):
    return MarcadasComoLidasResponse(marcadas=await marcar_todas_lidas(db, usuario.id))


@router.post(
    "/{notificacao_id}/lida",
    response_model=NotificacaoResponse,
    summary="Marcar uma notificação como lida",
    description=(
        "`notificacao_id` é o campo de mesmo nome da listagem. Idempotente: se já estava lida, "
        "devolve a notificação com o `lida_em` original. Notificação de outra pessoa ou "
        "inexistente dá 404 (nunca 403), para não revelar que existe."
    ),
    responses=respostas_de_erro({**ERROS_AUTENTICACAO, 404: "Notificação não encontrada"}),
)
async def marcar_uma(
    notificacao_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await marcar_lida(db, usuario.id, notificacao_id)
