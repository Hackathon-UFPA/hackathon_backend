from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FaseRubrica
from app.db.db import get_session
from app.models import Usuario
from app.schemas.rubrica import RubricaRascunhoResponse, RubricaResponse, RubricaUpdate
from app.security.dependencias import exigir_papeis
from app.security.permissoes import PERFIS_QUE_GERENCIAM_TEMAS_E_RUBRICAS
from app.services import rubrica as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/hackathons/{hackathon_id}/rubrica", tags=["Rubrica"])

gerencia_rubricas = exigir_papeis(*PERFIS_QUE_GERENCIAM_TEMAS_E_RUBRICAS)

# Cada edição tem uma rubrica por fase (BE-S5-08). Sem o parâmetro, vale a da proposta, que é
# a que já existia antes: os clientes atuais continuam funcionando sem mudança.
FASE = Query(
    default=FaseRubrica.PROPOSTA,
    description="PROPOSTA (avaliação científica, padrão) ou PROJETO_FINAL.",
)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ERRO_409_PUBLICADA = "A rubrica já foi publicada e não pode mais ser alterada (RN09)"


@router.get(
    "",
    response_model=RubricaResponse,
    summary="Consultar rubrica publicada (público)",
    description=(
        "**Não exige login** (RF17). Mostra critérios, pesos e escalas da rubrica publicada da "
        "edição na fase pedida (`fase`, padrão PROPOSTA), na ordem cadastrada. A versão "
        "publicada não muda durante o evento (RN09). Enquanto não há publicação, retorna 404."
    ),
    responses=respostas_de_erro({404: "Hackathon não encontrado ou rubrica não publicada"}),
)
async def obter_rubrica_publicada(
    hackathon_id: UUID, fase: FaseRubrica = FASE, db: AsyncSession = Depends(get_session)
):
    return await service.consultar_publicada(db, hackathon_id, fase)


@router.get(
    "/rascunho",
    response_model=RubricaRascunhoResponse,
    summary="Consultar rubrica em edição",
    description=(
        "Comitê Científico, Organizador (exceção administrativa) ou DEV. Retorna a rubrica da "
        "fase pedida, publicada ou não, e em `pendencias` o que ainda impede a publicação "
        "(soma dos pesos, critérios da RN10)."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Hackathon ou rubrica não encontrado"}
    ),
)
async def obter_rascunho(
    hackathon_id: UUID,
    fase: FaseRubrica = FASE,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_rubricas),
):
    return await service.consultar_rascunho(db, hackathon_id, fase)


@router.put(
    "",
    response_model=RubricaRascunhoResponse,
    summary="Salvar critérios da rubrica",
    description=(
        "Comitê Científico, Organizador (exceção administrativa) ou DEV (RF16). Cria a rubrica "
        "da fase pedida, se ainda não existe, e **substitui** a lista de critérios pela "
        "enviada; a ordem da lista é a de exibição. Critérios e pesos de uma fase não afetam "
        "a outra. "
        "Cada critério tem nome (único na rubrica), descrição, peso em % (maior que 0, até 2 "
        "casas) e escala (`escala_min` < `escala_max`). O rascunho pode ficar incompleto: a soma "
        "de 100% e os critérios mínimos da RN10 só são exigidos na publicação e aparecem em "
        "`pendencias`. Depois de publicada, retorna 409 (RN09)."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado", 409: ERRO_409_PUBLICADA}
    ),
)
async def salvar_rubrica(
    hackathon_id: UUID,
    dados: RubricaUpdate,
    fase: FaseRubrica = FASE,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_rubricas),
):
    return await service.salvar(db, hackathon_id, dados, fase)


@router.post(
    "/publicar",
    response_model=RubricaResponse,
    summary="Publicar rubrica",
    description=(
        "Comitê Científico, Organizador (exceção administrativa) ou DEV (RF16, RF17). Exige "
        "pelo menos um critério, soma dos pesos igual a 100% e todos os critérios mínimos da "
        "RN10. A rubrica da PROPOSTA precisa ser publicada antes do início das inscrições "
        "(`hackathon.inscricoes_inicio`, em UTC; sem data configurada é permitido); a do "
        "PROJETO_FINAL, antes da homologação do resultado das propostas. "
        "A publicação é única: a partir daí a rubrica não pode ser alterada (RN09)."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon ou rubrica não encontrado",
            409: "Rubrica já publicada ou fora da janela de publicação da fase",
            422: "Soma dos pesos diferente de 100% ou critérios da RN10 ausentes",
        }
    ),
)
async def publicar_rubrica(
    hackathon_id: UUID,
    fase: FaseRubrica = FASE,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_rubricas),
):
    return await service.publicar(db, hackathon_id, fase)
