from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.feedback_mentoria import (
    FeedbackMentoriaCreate,
    FeedbackMentoriaResponse,
    ItemHistorico,
)
from app.security.dependencias import exigir_papeis, usuario_ativo
from app.services import feedback_mentoria as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(
    tags=["Feedbacks da mentoria"],
    responses=respostas_de_erro(
        {
            401: "JWT ausente, inválido ou conta desativada.",
            403: "Conta pendente ou perfil sem permissão.",
        }
    ),
)

Db = Annotated[AsyncSession, Depends(get_session)]
UsuarioAtivo = Annotated[Usuario, Depends(usuario_ativo)]
Mentor = Annotated[Usuario, Depends(exigir_papeis(PapelUsuario.MENTOR))]
Limite = Annotated[int, Query(ge=1, le=100)]
Deslocamento = Annotated[int, Query(ge=0)]
ChaveIdempotencia = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        description=(
            "Opcional. Repetir o pedido com a mesma chave e o mesmo conteúdo devolve o feedback "
            "já criado (200). A mesma chave com outro conteúdo dá 409."
        ),
    ),
]
EscopoNegado = "Equipe inexistente ou fora do escopo do usuário (mesma resposta nos dois casos)."


@router.post(
    "/equipes/{equipe_id}/mentoria/feedbacks",
    response_model=FeedbackMentoriaResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "model": FeedbackMentoriaResponse,
            "description": "Repetição da mesma Idempotency-Key",
        },
        **respostas_de_erro(
            {
                404: "Equipe inexistente, de outra organização ou sem este mentor vigente.",
                409: (
                    "Equipe inelegível, edição finalizada ou cancelada, feedback já corrigido ou "
                    "Idempotency-Key com outro conteúdo."
                ),
                422: (
                    "Payload inválido, entrega ou marco fora da equipe e da edição, "
                    "ou correção inválida."
                ),
            }
        ),
    },
)
async def registrar_feedback(
    equipe_id: UUID,
    dados: FeedbackMentoriaCreate,
    response: Response,
    db: Db,
    mentor: Mentor,
    idempotency_key: ChaveIdempotencia = None,
):
    """Mentor com atribuição vigente na equipe (e DEV). O autor vem sempre do JWT.

    O feedback é imutável. Para corrigir, envie um novo com `corrige_id`: o original continua
    na listagem, marcado com `corrigido_por_id`. Os integrantes confirmados da equipe recebem
    uma notificação in-app (sem o texto) e nenhum e-mail.
    """
    feedback, criado = await service.registrar(db, mentor, equipe_id, dados, idempotency_key)
    if not criado:
        response.status_code = status.HTTP_200_OK
    return feedback


@router.get(
    "/equipes/{equipe_id}/mentoria/feedbacks",
    response_model=list[FeedbackMentoriaResponse],
    responses=respostas_de_erro({404: EscopoNegado}),
)
async def listar_feedbacks(
    equipe_id: UUID,
    db: Db,
    usuario: UsuarioAtivo,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
):
    """Integrantes da equipe, mentor vigente, gestores da organização da edição e DEV.

    Do mais recente ao mais antigo, inclusive os de mentores anteriores. Continua disponível
    com a edição encerrada.
    """
    return await service.listar(db, usuario, equipe_id, limite, deslocamento)


@router.get(
    "/equipes/{equipe_id}/mentoria/historico",
    response_model=list[ItemHistorico],
    responses=respostas_de_erro({404: EscopoNegado}),
)
async def historico_mentoria(
    equipe_id: UUID,
    db: Db,
    usuario: UsuarioAtivo,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
):
    """Mesmas permissões da listagem de feedbacks.

    Linha do tempo de entregas e feedbacks, do mais recente ao mais antigo. Cada item traz
    `tipo` (`ENTREGA` ou `FEEDBACK`), `ocorrido_em` e o objeto do tipo. A submissão final fica
    fora, como na listagem de entregas.
    """
    return await service.historico(db, usuario, equipe_id, limite, deslocamento)
