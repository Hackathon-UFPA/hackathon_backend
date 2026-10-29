from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.inscricao import (
    ConclusaoInscricaoResponse,
    PainelEquipeResponse,
    ReavaliacaoResponse,
)
from app.security.dependencias import exigir_papeis, usuario_ativo
from app.services.inscricao import concluir, painel, reavaliar_hackathon
from app.utils.openapi import respostas_de_erro

router = APIRouter(tags=["Inscrição"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"


@router.get(
    "/equipes/{equipe_id}/painel",
    response_model=PainelEquipeResponse,
    summary="Painel da equipe",
    description=(
        "Estado da inscrição para os integrantes acompanharem (RF25): a situação da equipe, "
        "cada integrante com o estado do convite, dos termos e do comprovante, e a lista do "
        "que ainda falta (`pendencias`). Convites sem resposta ou recusados aparecem com "
        "`integrante = false`. `pode_concluir` diz se a ação de concluir deve aparecer: só "
        "o líder a vê (RN03). Restrito a integrantes da equipe, com a exceção técnica DEV."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Equipe não encontrada"}),
)
async def painel_da_equipe(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await painel(db, usuario, equipe_id)


@router.post(
    "/equipes/{equipe_id}/inscricao/concluir",
    response_model=ConclusaoInscricaoResponse,
    summary="Concluir inscrição da equipe",
    description=(
        "O líder oficializa a participação (RF22, RN03). Exige inscrições abertas (RN06), de "
        "`min_integrantes` a `max_integrantes` (3 a 5 por padrão, Q04 em aberto) e que todos "
        "tenham convite aceito, conta ativa e os termos vigentes aceitos (RN01, RN05), o "
        "líder inclusive. Convites sem resposta são cancelados e a equipe passa a "
        "`AGUARDANDO_HOMOLOGACAO`, com protocolo emitido na resposta como confirmação. Se o "
        "vínculo de todos já estiver aprovado, a equipe é homologada na mesma chamada (RF23). "
        "O aviso por e-mail depende da infraestrutura de e-mail, que ainda não existe. Em "
        "caso de bloqueio, `GET /equipes/{id}/painel` mostra tudo o que falta."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: "Quem pede não é o líder da equipe, ou a conta está pendente",
            404: "Equipe não encontrada",
            409: "Inscrição já concluída, inscrições fechadas ou requisitos não cumpridos",
        }
    ),
)
async def concluir_inscricao(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await concluir(db, usuario, equipe_id)


@router.post(
    "/admin/hackathons/{hackathon_id}/equipes/reavaliar",
    response_model=ReavaliacaoResponse,
    summary="Reavaliar a homologação das equipes",
    description=(
        "Refaz a homologação automática de todas as equipes com inscrição concluída (RF23). "
        "Equipes que cumprem os requisitos passam a `HOMOLOGADA`, e as homologadas que "
        "deixaram de cumprir (por exemplo, depois de uma nova versão dos termos) voltam a "
        "`AGUARDANDO_HOMOLOGACAO`. As mudanças de comprovante já reavaliam a equipe "
        "sozinhas; use esta rota para o que muda fora disso. Restrito ao Organizador."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado"}),
)
async def reavaliar_equipes(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(exigir_papeis(PapelUsuario.ORGANIZADOR)),
):
    return await reavaliar_hackathon(db, hackathon_id)
