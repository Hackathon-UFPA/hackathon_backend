from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusComprovante
from app.db.db import get_session
from app.models import Usuario
from app.schemas.comprovante_vinculo import (
    ComprovanteAdminResponse,
    ComprovanteEnvio,
    ComprovanteRecusa,
    ComprovanteVinculoResponse,
)
from app.security.dependencias import exigir_papeis, usuario_atual
from app.security.organizacao import conferente_do_comprovante
from app.security.permissoes import PERFIS_QUE_VALIDAM_COMPROVANTE
from app.services.comprovante_vinculo import aprovar, listar, listar_meus, recusar, reenviar
from app.utils.openapi import respostas_de_erro

router = APIRouter(tags=["Comprovantes"])

conferente = exigir_papeis(*PERFIS_QUE_VALIDAM_COMPROVANTE)
conferente_do_item = conferente_do_comprovante(*PERFIS_QUE_VALIDAM_COMPROVANTE)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403_ADMIN = "Perfil sem permissão para conferir comprovantes, ou conta pendente"


@router.get(
    "/admin/comprovantes",
    response_model=list[ComprovanteAdminResponse],
    summary="Fila de comprovantes",
    description=(
        "Lista os comprovantes de vínculo para conferência (RF21), do mais antigo ao mais novo, "
        "com `arquivo_url` para abrir o documento e os dados de quem enviou. Por padrão traz "
        "só os `PENDENTE`. Restrito a Organizador e Comitê Científico (Q25 em aberto)."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403_ADMIN}),
)
async def fila_de_comprovantes(
    situacao: StatusComprovante = Query(default=StatusComprovante.PENDENTE, alias="status"),
    hackathon_id: UUID | None = None,
    limite: int = Query(default=50, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    conferente_logado: Usuario = Depends(conferente),
):
    return await listar(
        db,
        status=situacao,
        hackathon_id=hackathon_id,
        limite=limite,
        deslocamento=deslocamento,
        conferente=conferente_logado,
    )


@router.post(
    "/admin/comprovantes/{comprovante_id}/aprovar",
    response_model=ComprovanteAdminResponse,
    summary="Aprovar comprovante",
    description=(
        "Aprova o vínculo (RN25). A conta de quem enviou passa a `ATIVA` e a equipe dele é "
        "reavaliada: se todos os integrantes já têm vínculo aprovado e termos aceitos, ela é "
        "homologada na hora (RF23). Só comprovantes `PENDENTE` podem ser decididos. "
        "A aprovação não envia e-mail específico sobre o comprovante; se a reavaliação "
        "homologar a equipe, o aviso de equipe homologada entra na fila de e-mails."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403_ADMIN,
            404: "Comprovante não encontrado",
            409: "Comprovante já aprovado ou recusado",
        }
    ),
)
async def aprovar_comprovante(
    comprovante_id: UUID,
    db: AsyncSession = Depends(get_session),
    validador: Usuario = Depends(conferente_do_item),
):
    return await aprovar(db, validador, comprovante_id)


@router.post(
    "/admin/comprovantes/{comprovante_id}/recusar",
    response_model=ComprovanteAdminResponse,
    summary="Recusar comprovante",
    description=(
        "Recusa o comprovante e registra o motivo (obrigatório). Quem enviou vê o motivo em "
        "`GET /comprovantes/meus` e pode mandar outro com `POST /comprovantes`. A conta "
        "continua `PENDENTE`. A recusa não dispara notificação por e-mail; o motivo fica "
        "disponível para consulta."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403_ADMIN,
            404: "Comprovante não encontrado",
            409: "Comprovante já aprovado ou recusado",
        }
    ),
)
async def recusar_comprovante(
    comprovante_id: UUID,
    dados: ComprovanteRecusa,
    db: AsyncSession = Depends(get_session),
    validador: Usuario = Depends(conferente_do_item),
):
    return await recusar(db, validador, comprovante_id, dados.motivo_recusa)


# Estas duas rotas aceitam conta pendente: quem teve o comprovante recusado ainda não pode
# usar o resto da API, mas precisa ver o motivo e enviar outro.
@router.get(
    "/comprovantes/meus",
    response_model=list[ComprovanteVinculoResponse],
    summary="Meus comprovantes",
    description=(
        "Histórico dos comprovantes de quem está logado, do mais recente ao mais antigo, com a "
        "situação e o `motivo_recusa` quando houver. Funciona com a conta pendente."
    ),
    responses=respostas_de_erro({401: ERRO_401}),
)
async def meus_comprovantes(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_atual)
):
    return await listar_meus(db, usuario)


@router.post(
    "/comprovantes",
    response_model=ComprovanteVinculoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar comprovante de vínculo",
    description=(
        "Envia o comprovante de vínculo para participar de um hackathon (RF21). A organização "
        "dona do hackathon confere e aprova. Depois de uma recusa, serve para mandar outro; o "
        "anterior fica no histórico. Exige inscrições abertas no hackathon informado."
        " Sem hackathon_id no corpo, só aceita uma edição elegível; várias retornam 409."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            404: "Hackathon não encontrado",
            409: "Comprovante ativo existente, inscrições indisponíveis ou edição ambígua",
            422: "Campos inválidos, inclusive hackathon_id fora do formato UUID",
        }
    ),
)
async def enviar_comprovante(
    dados: ComprovanteEnvio,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_atual),
):
    return await reenviar(db, usuario, dados)
