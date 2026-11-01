from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.submissao import (
    SubmissaoCreate,
    SubmissaoEnviadaResponse,
    SubmissaoResponse,
    SubmissaoUpdate,
)
from app.security.dependencias import usuario_ativo
from app.services.submissao import consultar_enviada, consultar_rascunho, criar, editar, enviar
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/equipes/{equipe_id}/proposta/rascunho", tags=["Propostas"])
router_proposta = APIRouter(prefix="/equipes/{equipe_id}/proposta", tags=["Propostas"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ERRO_404 = "Equipe, rascunho ou tema não encontrado"
ERRO_409 = "Proposta existente ou enviada, equipe em somente leitura ou tema indisponível"


@router.post(
    "",
    response_model=SubmissaoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar rascunho de proposta",
    description=(
        "Somente o líder técnico da equipe ou DEV, com conta ativa, pode criar um rascunho "
        "(RF27). Aceita corpo vazio e campos incompletos. O tema é opcional; quando informado, "
        "deve estar ativo e pertencer à edição da equipe. Existe apenas uma proposta por equipe. "
        "Equipe, edição, status e datas são definidos pelo servidor. Não exige homologação ou "
        "prazo de envio definitivo. Equipes NAO_HOMOLOGADA ficam em somente leitura (RF34)."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: ERRO_404, 409: ERRO_409}),
)
async def criar_rascunho(
    equipe_id: UUID,
    dados: SubmissaoCreate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await criar(db, usuario, equipe_id, dados)


@router.get(
    "",
    response_model=SubmissaoResponse,
    summary="Consultar rascunho de proposta",
    description=(
        "Somente integrantes da equipe ou DEV, com conta ativa, podem consultar o rascunho. "
        "Retorna o conteúdo e atualizado_em, a data do último salvamento. Propostas ENVIADA "
        "não são retornadas como rascunho. Não disponibiliza rascunhos para avaliação."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: ERRO_404}),
)
async def obter_rascunho(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await consultar_rascunho(db, usuario, equipe_id)


@router.patch(
    "",
    response_model=SubmissaoResponse,
    summary="Salvar alterações do rascunho",
    description=(
        "Somente o líder técnico ou DEV, com conta ativa. Altera apenas campos informados, "
        "aceita null para limpar campos opcionais e atualiza atualizado_em em cada salvamento. "
        "Valida o tema somente quando tema_id é informado. Propostas ENVIADA e equipes "
        "NAO_HOMOLOGADA não podem ser alteradas, inclusive por DEV. Não realiza envio definitivo."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: ERRO_404, 409: ERRO_409}),
)
async def editar_rascunho(
    equipe_id: UUID,
    dados: SubmissaoUpdate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await editar(db, usuario, equipe_id, dados)


@router_proposta.post(
    "/enviar",
    response_model=SubmissaoEnviadaResponse,
    summary="Enviar proposta definitiva e emitir protocolo",
    description=(
        "RF26/RF28: somente líder técnico ou DEV com conta ativa. Exige equipe HOMOLOGADA, "
        "rascunho completo, tema ativo da mesma edição e ambos os limites do prazo de propostas "
        "configurados, com o momento atual no intervalo inclusivo em UTC. documento_url é "
        "opcional. O envio torna a proposta imutável e emite um protocolo PROPOSTA na mesma "
        "transação. Reenvio retorna 409. A resposta inclui enviado_em, protocolo.numero e "
        "protocolo.emitido_em. Não envia e-mail."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: ERRO_404,
            409: "Proposta enviada, equipe não homologada, tema indisponível ou prazo fechado",
            422: "Campos obrigatórios da proposta incompletos ou inválidos",
        }
    ),
)
async def enviar_proposta(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await enviar(db, usuario, equipe_id)


@router_proposta.get(
    "",
    response_model=SubmissaoEnviadaResponse,
    summary="Consultar proposta enviada e protocolo",
    description=(
        "Somente integrantes da equipe ou DEV com conta ativa. Retorna conteúdo, status, "
        "enviado_em e protocolo persistido. Rascunhos não são expostos; sem proposta enviada "
        "retorna 404. O protocolo também pode ser consultado no campo protocolo_proposta do painel."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Equipe ou proposta enviada não encontrada"}
    ),
)
async def obter_proposta_enviada(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await consultar_enviada(db, usuario, equipe_id)
