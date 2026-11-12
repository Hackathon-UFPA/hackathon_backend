from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusEmail, TipoEmail
from app.db.db import get_session
from app.models import Usuario
from app.schemas.email import EmailResponse
from app.security.dependencias import exigir_papeis
from app.security.permissoes import PERFIS_QUE_ACOMPANHAM_EMAILS
from app.services.email import consultar, listar, reenviar
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/admin/emails", tags=["E-mails"])

acompanha_emails = exigir_papeis(*PERFIS_QUE_ACOMPANHAM_EMAILS)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Perfil sem permissão para acompanhar os e-mails, ou conta pendente"


@router.get(
    "",
    response_model=list[EmailResponse],
    summary="Listar e-mails da fila",
    description=(
        "RNF28. Acompanha o envio dos e-mails transacionais (convites, protocolos, resultado...). "
        "Os mais recentes vêm primeiro. Filtros opcionais: `status`, `tipo` e `destinatario` "
        "(e-mail exato, sem diferenciar maiúsculas). Paginação por `limite` (1 a 100, padrão 50) "
        "e `deslocamento`. A resposta traz só a situação do envio, nunca o conteúdo da mensagem. "
        "Restrito a Organizador (e DEV)."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403}),
)
async def listar_emails(
    situacao: StatusEmail | None = Query(
        default=None, alias="status", description="Filtra pela situação do envio"
    ),
    tipo: TipoEmail | None = Query(default=None, description="Filtra pelo tipo de e-mail"),
    destinatario: str | None = Query(
        default=None, max_length=320, description="E-mail do destinatário"
    ),
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(acompanha_emails),
):
    return await listar(
        db,
        status=situacao,
        tipo=tipo,
        destinatario=destinatario,
        limite=limite,
        deslocamento=deslocamento,
    )


@router.get(
    "/{email_id}",
    response_model=EmailResponse,
    summary="Consultar um e-mail da fila",
    description=(
        "RNF28. Situação de um e-mail: tentativas, próxima tentativa, último erro e data do "
        "envio. Não traz o conteúdo da mensagem. Restrito a Organizador (e DEV)."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "E-mail não encontrado"}),
)
async def consultar_email(
    email_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(acompanha_emails),
):
    return await consultar(db, email_id)


@router.post(
    "/{email_id}/reenviar",
    response_model=EmailResponse,
    summary="Reenviar um e-mail que falhou",
    description=(
        "RNF28. Devolve à fila um e-mail em `FALHA` (erro permanente do provedor ou "
        "tentativas esgotadas), com as tentativas zeradas; o worker o envia na próxima rodada. "
        "E-mails `PENDENTE` ou `ENVIANDO` já estão na fila e os `ENVIADO` já foram entregues, "
        "então reenviá-los duplicaria o aviso: respondem 409. Restrito a Organizador (e DEV)."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "E-mail não encontrado",
            409: "O e-mail não está em FALHA (já foi enviado ou ainda está na fila)",
        }
    ),
)
async def reenviar_email(
    email_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(acompanha_emails),
):
    return await reenviar(db, email_id)
