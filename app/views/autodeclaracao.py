from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.autodeclaracao import (
    AutodeclaracaoEnvio,
    AutodeclaracaoResponse,
    AutodeclaracaoSituacaoResponse,
)
from app.security.dependencias import usuario_atual
from app.services.autodeclaracao import declarar, situacao
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/me/autodeclaracao", tags=["Autodeclaração"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Só participantes declaram o próprio vínculo"
ERRO_409 = "Não há hackathon com inscrições abertas no momento"

# As duas rotas aceitam conta pendente: quem ainda espera a conferência do comprovante já pode e
# precisa declarar o próprio vínculo.


@router.get(
    "",
    response_model=AutodeclaracaoSituacaoResponse,
    summary="Minha autodeclaração e a comprovação do vínculo",
    description=(
        "Mostra, para a edição com inscrições abertas, a declaração mais recente e o histórico de "
        "declarações de quem está logado, ao lado do comprovante do vínculo que vale para a "
        "pessoa (BE-S5-03). `vinculo_comprovado` só é verdadeiro com comprovante `APROVADO`: "
        "declarar não comprova nada. Não traz o link do documento. Funciona com a conta "
        "pendente."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 409: ERRO_409}),
)
async def minha_autodeclaracao(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_atual)
):
    return await situacao(db, usuario)


@router.put(
    "",
    response_model=AutodeclaracaoResponse,
    summary="Declarar o meu vínculo",
    description=(
        "A própria pessoa declara o vínculo (RF01, RN25): `ESTUDANTE` com `instituicao`, `curso` e "
        "`periodo`, ou `PROFISSIONAL` com `organizacao` e `cargo`. Campos do outro tipo ou "
        "desconhecidos dão 422. O usuário vem do token: não há como declarar por outra pessoa, "
        "nem o líder. Cada mudança grava uma declaração nova, sem apagar as anteriores "
        "(auditoria); repetir a declaração atual não grava nada. A equipe é reavaliada: se o tipo "
        "declarado contradiz o que o líder indicou, a equipe sai da homologação (pendência "
        "`TIPO_DIVERGENTE`) até alguém corrigir. Vale para a edição com inscrições abertas. "
        "Funciona com a conta pendente."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            409: ERRO_409,
            422: "Campos obrigatórios do tipo ausentes, campos do outro tipo ou valores inválidos",
        }
    ),
)
async def declarar_vinculo(
    dados: AutodeclaracaoEnvio,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_atual),
):
    return await declarar(db, usuario, dados)
