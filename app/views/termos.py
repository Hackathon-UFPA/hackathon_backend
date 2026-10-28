from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.aceite_termo import AceiteTermoResponse, AceiteTermosCreate
from app.schemas.termo import TermoResponse
from app.security.dependencias import usuario_ativo
from app.services.termo import aceitar_termos, termos_vigentes_do_hackathon
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/hackathons/{hackathon_id}/termos", tags=["Termos"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente"


@router.get(
    "/vigentes",
    response_model=list[TermoResponse],
    summary="Termos vigentes",
    description=(
        "Regulamento e termo de consentimento em vigor, com `versao`, `titulo` e o `conteudo` "
        "ou a `url` do documento, para a pessoa ler antes de aceitar (RF20). Os ids daqui são "
        "os que se enviam ao aceitar."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado"}),
)
async def termos_vigentes(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(usuario_ativo),
):
    return await termos_vigentes_do_hackathon(db, hackathon_id)


@router.post(
    "/aceites",
    response_model=list[AceiteTermoResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Aceitar regulamento e termo de consentimento",
    description=(
        "Registra o aceite de quem está logado às versões **vigentes** do regulamento e do "
        "termo de consentimento (RF20, RN05), com data e hora do servidor. É preciso enviar "
        "os dois. Repetir o aceite da mesma versão não muda o registro original."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: "Termos não publicados, ou ids que não são os vigentes",
            422: "Faltou aceitar o regulamento ou o termo de consentimento",
        }
    ),
)
async def aceitar(
    hackathon_id: UUID,
    dados: AceiteTermosCreate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await aceitar_termos(db, usuario, hackathon_id, dados.termos_ids)
