from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.resultado import (
    HomologacaoCreate,
    PropostasAprovadasResponse,
    ResultadoAvaliacaoResponse,
)
from app.security.dependencias import exigir_papeis
from app.services.resultado import consultar_resultado, homologar, listar_propostas_aprovadas
from app.utils.openapi import respostas_de_erro

router_admin = APIRouter(prefix="/admin/hackathons/{hackathon_id}/resultado", tags=["Resultado"])
router_publico = APIRouter(prefix="/hackathons/{hackathon_id}", tags=["Resultado"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ORGANIZADOR = exigir_papeis(PapelUsuario.ORGANIZADOR)


@router_admin.get(
    "",
    response_model=ResultadoAvaliacaoResponse,
    summary="Consultar o resultado consolidado da avaliação",
    description=(
        "RF31. Organizador (e DEV). Lista cada proposta ENVIADA com a média das notas finais "
        "enviadas pelos avaliadores designados, a classificação (maior média primeiro; "
        "empate por mais recomendações de aprovação, depois por quem enviou antes) e a "
        "contagem de recomendações. `pendencias` mostra o que ainda impede homologar e "
        "`pode_homologar` indica se o botão pode ser habilitado. Depois da homologação "
        "devolve o resultado oficial, que não muda mais, com quem homologou e quando."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado"}),
)
async def resultado_da_avaliacao(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(ORGANIZADOR),
):
    return await consultar_resultado(db, hackathon_id)


@router_admin.post(
    "/homologar",
    response_model=ResultadoAvaliacaoResponse,
    summary="Homologar o resultado da avaliação",
    description=(
        "RF31. Organizador (e DEV). Oficializa o resultado: `propostas_aprovadas` lista as "
        "propostas aprovadas e as demais ficam reprovadas. Só é possível com todas as "
        "avaliações concluídas (cada proposta ENVIADA com a quantidade configurada de "
        "avaliadores e todos com avaliação enviada). Grava quem homologou, quando e um "
        "retrato das notas e da classificação. Depois disso o resultado fica bloqueado: "
        "homologar de novo, avaliar, distribuir, redistribuir ou reconfigurar a quantidade "
        "de avaliadores respondem 409. A lista de aprovadas passa a ser pública."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: "Resultado já homologado ou avaliações ainda não concluídas",
            422: "Lista com repetidos ou com proposta que não é ENVIADA deste hackathon",
        }
    ),
)
async def homologar_resultado(
    hackathon_id: UUID,
    dados: HomologacaoCreate,
    db: AsyncSession = Depends(get_session),
    organizador: Usuario = Depends(ORGANIZADOR),
):
    return await homologar(db, organizador, hackathon_id, dados.propostas_aprovadas)


@router_publico.get(
    "/propostas-aprovadas",
    response_model=PropostasAprovadasResponse,
    summary="Propostas aprovadas (público)",
    description=(
        "RF32. Não exige login. Depois da homologação, lista as propostas aprovadas com "
        "equipe, tema e título, em ordem alfabética pela equipe (sem notas nem "
        "classificação). Antes disso responde 200 com `divulgado = false` e lista vazia: "
        "nenhum resultado não homologado é exposto."
    ),
    responses=respostas_de_erro({404: "Hackathon não encontrado"}),
)
async def propostas_aprovadas(hackathon_id: UUID, db: AsyncSession = Depends(get_session)):
    return await listar_propostas_aprovadas(db, hackathon_id)
