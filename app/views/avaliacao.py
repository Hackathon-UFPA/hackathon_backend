from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.designacao_avaliacao import (
    ConfiguracaoAvaliacaoResponse,
    ConfiguracaoAvaliacaoUpdate,
    DistribuicaoResponse,
    PropostaDesignadaAdminResponse,
    PropostaParaAvaliacaoResponse,
    RedistribuicaoCreate,
)
from app.security.dependencias import exigir_papeis
from app.services.designacao_avaliacao import (
    configurar,
    consultar_minha_proposta,
    distribuir,
    listar_designacoes,
    listar_minhas_propostas,
    redistribuir,
)
from app.utils.openapi import respostas_de_erro

router_admin = APIRouter(tags=["Avaliação"])
router_avaliador = APIRouter(prefix="/avaliador/propostas", tags=["Avaliação"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ORGANIZADOR = exigir_papeis(PapelUsuario.ORGANIZADOR)
AVALIADOR = exigir_papeis(PapelUsuario.COMITE_CIENTIFICO)


@router_admin.patch(
    "/admin/hackathons/{hackathon_id}/avaliacao/configuracao",
    response_model=ConfiguracaoAvaliacaoResponse,
    summary="Configurar avaliadores por proposta",
    description=(
        "Organizador (e DEV). Define de 2 a 3 avaliadores por proposta (Q07). Não há valor "
        "padrão: enquanto não for configurado, distribuir responde 409. Alterar a quantidade "
        "vale só para as próximas distribuições e NÃO mexe nas designações já feitas nem nas "
        "notas; uma proposta com mais ou menos avaliadores que o novo valor só muda se for "
        "redistribuída (PUT) ou completada por uma nova distribuição."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado", 422: "Valor fora de 2 a 3"}
    ),
)
async def configurar_avaliacao(
    hackathon_id: UUID,
    dados: ConfiguracaoAvaliacaoUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(ORGANIZADOR),
):
    return await configurar(db, hackathon_id, dados.avaliadores_por_proposta)


@router_admin.post(
    "/admin/hackathons/{hackathon_id}/avaliacoes/distribuir",
    response_model=DistribuicaoResponse,
    summary="Distribuir propostas entre os avaliadores",
    description=(
        "RF29. Organizador (e DEV). Distribui as propostas ENVIADA do hackathon: cada uma "
        "recebe a quantidade configurada de avaliadores, sempre escolhendo quem tem menos "
        "propostas (desempate pelo id). Rascunhos não entram. Avaliador elegível é Comitê "
        "Científico com conta ativa; hoje não existe vínculo avaliador-hackathon, então vale "
        "todo elegível do sistema. Rodar de novo só completa as propostas incompletas e não "
        "altera as demais. Se faltar avaliador elegível para alguma proposta, responde 409 e "
        "não grava nada. Bloqueado com o hackathon EM_AVALIACAO, FINALIZADO ou CANCELADO; "
        "propostas que já têm nota são ignoradas."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: (
                "Quantidade não configurada, avaliação já iniciada (ou hackathon "
                "finalizado/cancelado) ou avaliadores elegíveis insuficientes"
            ),
        }
    ),
)
async def distribuir_propostas(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    organizador: Usuario = Depends(ORGANIZADOR),
):
    return await distribuir(db, organizador, hackathon_id)


@router_admin.put(
    "/admin/propostas/{submissao_id}/avaliadores",
    response_model=PropostaDesignadaAdminResponse,
    summary="Redistribuir uma proposta",
    description=(
        "RF29. Organizador (e DEV). Substitui os avaliadores da proposta pela lista "
        "`avaliador_ids`, que precisa ter exatamente a quantidade configurada, sem repetidos, "
        "todos Comitê Científico com conta ativa (DEV não é avaliador). Quem continua na lista "
        "mantém a designação. Só é possível antes de a avaliação começar: 409 se o hackathon "
        "estiver EM_AVALIACAO, FINALIZADO ou CANCELADO, se a proposta já tiver nota ou se não "
        "estiver ENVIADA."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Proposta não encontrada",
            409: (
                "Quantidade não configurada, avaliação já iniciada, proposta com nota ou "
                "não enviada, ou avaliador não elegível"
            ),
            422: "Lista com quantidade diferente da configurada ou com avaliadores repetidos",
        }
    ),
)
async def redistribuir_proposta(
    submissao_id: UUID,
    dados: RedistribuicaoCreate,
    db: AsyncSession = Depends(get_session),
    organizador: Usuario = Depends(ORGANIZADOR),
):
    return await redistribuir(db, organizador, submissao_id, dados.avaliador_ids)


@router_admin.get(
    "/admin/hackathons/{hackathon_id}/avaliacoes/designacoes",
    response_model=list[PropostaDesignadaAdminResponse],
    summary="Listar designações do hackathon",
    description=(
        "Organizador (e DEV). Lista cada proposta ENVIADA com os avaliadores designados; "
        "`avaliadores` vem vazio enquanto a proposta não foi distribuída."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado"}),
)
async def listar_designacoes_do_hackathon(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(ORGANIZADOR),
):
    return await listar_designacoes(db, hackathon_id)


@router_avaliador.get(
    "",
    response_model=list[PropostaParaAvaliacaoResponse],
    summary="Listar minhas propostas designadas",
    description=(
        "Comitê Científico (e DEV, que também vê só o que foi designado a ele). Retorna "
        "somente as propostas designadas a quem está logado. Não traz a equipe."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403}),
)
async def minhas_propostas(
    db: AsyncSession = Depends(get_session),
    avaliador: Usuario = Depends(AVALIADOR),
):
    return await listar_minhas_propostas(db, avaliador)


@router_avaliador.get(
    "/{submissao_id}",
    response_model=PropostaParaAvaliacaoResponse,
    summary="Consultar uma proposta designada",
    description=(
        "Comitê Científico (e DEV). Retorna a proposta só se estiver designada a quem está "
        "logado; qualquer outra responde 404, sem revelar que ela existe."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Proposta não encontrada ou não designada a você"}
    ),
)
async def minha_proposta(
    submissao_id: UUID,
    db: AsyncSession = Depends(get_session),
    avaliador: Usuario = Depends(AVALIADOR),
):
    return await consultar_minha_proposta(db, avaliador, submissao_id)
