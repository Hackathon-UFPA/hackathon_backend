from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.designacao_projeto_final import (
    ConfiguracaoAvaliacaoTecnicaResponse,
    ConfiguracaoAvaliacaoTecnicaUpdate,
    ConflitoProjetoFinalCreate,
    ConflitoProjetoFinalResponse,
    DistribuicaoProjetosFinaisResponse,
    ProjetoFinalDesignadoAdminResponse,
    ProjetoFinalParaAvaliacaoResponse,
    RedistribuicaoProjetoFinalCreate,
)
from app.security.dependencias import exigir_papeis
from app.security.organizacao import gestor_da_proposta, gestor_do_hackathon
from app.services.designacao_projeto_final import (
    baixar_relatorio_do_meu_projeto,
    configurar,
    consultar_conflitos,
    consultar_meu_projeto,
    distribuir,
    listar_designacoes,
    listar_meus_projetos,
    redistribuir,
    registrar_conflito,
)
from app.utils.openapi import respostas_de_erro
from app.views.mentoria import RelatorioPDF, resposta_relatorio_pdf

router_admin = APIRouter(tags=["Avaliação técnica"])
router_avaliador = APIRouter(prefix="/comite-tecnico/projetos-finais", tags=["Avaliação técnica"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ERRO_ENCERRADO = "Hackathon finalizado ou cancelado"
ORGANIZADOR = gestor_do_hackathon(PapelUsuario.ORGANIZADOR)
ORGANIZADOR_DO_PROJETO = gestor_da_proposta(PapelUsuario.ORGANIZADOR)
AVALIADOR_TECNICO = exigir_papeis(PapelUsuario.COMITE_TECNICO)


@router_admin.patch(
    "/admin/hackathons/{hackathon_id}/avaliacao-tecnica/configuracao",
    response_model=ConfiguracaoAvaliacaoTecnicaResponse,
    summary="Configurar avaliadores por projeto final",
    description=(
        "Organizador (e DEV). Define de 2 a 3 avaliadores do Comitê Técnico por projeto final "
        "(Q07). Sem valor padrão: enquanto não for configurado, distribuir responde 409. "
        "Alterar vale só para as próximas distribuições e não mexe nas designações já feitas."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: ERRO_ENCERRADO,
            422: "Valor fora de 2 a 3",
        }
    ),
)
async def configurar_avaliacao_tecnica(
    hackathon_id: UUID,
    dados: ConfiguracaoAvaliacaoTecnicaUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(ORGANIZADOR),
):
    return await configurar(db, hackathon_id, dados.avaliadores_por_projeto_final)


@router_admin.post(
    "/admin/hackathons/{hackathon_id}/avaliacao-tecnica/distribuir",
    response_model=DistribuicaoProjetosFinaisResponse,
    summary="Distribuir projetos finais ao Comitê Técnico",
    description=(
        "RF47, RF48, RN13. Organizador (e DEV). Propostas aprovadas na homologação científica "
        "podem receber designações antecipadas. Antes da homologação, retorna 409. Cada "
        "projeto recebe a quantidade configurada de avaliadores do Comitê Técnico (conta ativa, "
        "mesma organização), sempre escolhendo quem tem menos projetos (desempate pelo id). Ficam "
        "de fora os integrantes da equipe, os mentores dela (inclusive atribuições encerradas) "
        "e os conflitos declarados. A operação revalida as designações vigentes e recompõe "
        "vagas de avaliadores inelegíveis. A falta de avaliadores retorna 409 e reverte a operação."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: (
                "Quantidade não configurada, resultado científico não homologado, hackathon "
                "encerrado ou avaliadores sem conflito insuficientes"
            ),
        }
    ),
)
async def distribuir_projetos_finais(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    organizador: Usuario = Depends(ORGANIZADOR),
):
    return await distribuir(db, organizador, hackathon_id)


@router_admin.put(
    "/admin/projetos-finais/{submissao_id}/avaliadores",
    response_model=ProjetoFinalDesignadoAdminResponse,
    summary="Redistribuir um projeto final",
    description=(
        "RF48. Organizador (e DEV). Substitui os avaliadores do projeto pela lista "
        "`avaliador_ids`: exatamente a quantidade configurada, sem repetidos, todos do Comitê "
        "Técnico com conta ativa e sem conflito com a equipe. Quem continua mantém a "
        "designação; quem sai fica no histórico como removido (com data e autor)."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Projeto final não encontrado (proposta inexistente ou não aprovada)",
            409: (
                "Quantidade não configurada, hackathon encerrado, avaliador não elegível "
                "ou em conflito de interesse"
            ),
            422: "Lista com quantidade diferente da configurada ou com avaliadores repetidos",
        }
    ),
)
async def redistribuir_projeto_final(
    submissao_id: UUID,
    dados: RedistribuicaoProjetoFinalCreate,
    db: AsyncSession = Depends(get_session),
    organizador: Usuario = Depends(ORGANIZADOR_DO_PROJETO),
):
    return await redistribuir(db, organizador, submissao_id, dados.avaliador_ids)


@router_admin.get(
    "/admin/hackathons/{hackathon_id}/avaliacao-tecnica/designacoes",
    response_model=list[ProjetoFinalDesignadoAdminResponse],
    summary="Listar designações dos projetos finais",
    description=(
        "Organizador (e DEV). Lista as propostas aprovadas, as designações vigentes e se "
        "cada projeto já possui uma submissão final válida (`pronto_para_avaliacao`)."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: "Resultado científico não homologado",
        }
    ),
)
async def listar_designacoes_projetos_finais(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(ORGANIZADOR),
):
    return await listar_designacoes(db, hackathon_id)


@router_admin.post(
    "/admin/hackathons/{hackathon_id}/avaliacao-tecnica/conflitos",
    response_model=ConflitoProjetoFinalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar conflito de interesse",
    description=(
        "RN13. Organizador (e DEV). Impede o avaliador do Comitê Técnico de ser designado ao "
        "projeto da equipe. Integrantes e mentores da equipe já são bloqueados sem registro. "
        "Se o avaliador já estiver designado ao projeto, responde 409: redistribua antes."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon, equipe ou avaliador do Comitê Técnico não encontrado",
            409: f"{ERRO_ENCERRADO}, conflito já registrado ou avaliador designado ao projeto",
            422: "Motivo vazio ou campos inválidos",
        }
    ),
)
async def registrar_conflito_projeto_final(
    hackathon_id: UUID,
    dados: ConflitoProjetoFinalCreate,
    db: AsyncSession = Depends(get_session),
    organizador: Usuario = Depends(ORGANIZADOR),
):
    return await registrar_conflito(
        db, organizador, hackathon_id, dados.equipe_id, dados.avaliador_id, dados.motivo
    )


@router_admin.get(
    "/admin/hackathons/{hackathon_id}/avaliacao-tecnica/conflitos",
    response_model=list[ConflitoProjetoFinalResponse],
    summary="Listar conflitos de interesse declarados",
    description="Organizador (e DEV). Conflitos registrados no hackathon, do mais antigo.",
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Hackathon não encontrado"}),
)
async def listar_conflitos_projeto_final(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(ORGANIZADOR),
):
    return await consultar_conflitos(db, hackathon_id)


@router_avaliador.get(
    "",
    response_model=list[ProjetoFinalParaAvaliacaoResponse],
    summary="Listar meus projetos finais designados",
    description=(
        "Projetos com designação vigente para o avaliador elegível e sem conflito de interesse. "
        "Quando já existe uma submissão final validada, inclui seus artefatos. Designações "
        "antecipadas aparecem com pronto_para_avaliacao=false."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403}),
)
async def meus_projetos_finais(
    db: AsyncSession = Depends(get_session),
    avaliador: Usuario = Depends(AVALIADOR_TECNICO),
):
    return await listar_meus_projetos(db, avaliador)


@router_avaliador.get(
    "/{submissao_id}",
    response_model=ProjetoFinalParaAvaliacaoResponse,
    summary="Consultar um projeto final designado",
    description=(
        "Somente o avaliador elegível com designação vigente e sem conflito de interesse "
        "pode consultar. Os artefatos ficam disponíveis depois de validar a submissão final."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403, 404: "Projeto não encontrado ou não designado a você"}
    ),
)
async def meu_projeto_final(
    submissao_id: UUID,
    db: AsyncSession = Depends(get_session),
    avaliador: Usuario = Depends(AVALIADOR_TECNICO),
):
    return await consultar_meu_projeto(db, avaliador, submissao_id)


@router_avaliador.get(
    "/{submissao_id}/relatorio",
    response_class=Response,
    summary="Baixar o relatório de um projeto final designado",
    description=(
        "Requer designação vigente, avaliador elegível sem conflito e submissão final válida."
    ),
    responses={
        200: {"description": "PDF do relatório final", "content": RelatorioPDF},
        **respostas_de_erro(
            {401: ERRO_401, 403: ERRO_403, 404: "Projeto ou relatório indisponível ao avaliador."}
        ),
    },
)
async def baixar_relatorio_do_projeto(
    submissao_id: UUID,
    db: AsyncSession = Depends(get_session),
    avaliador: Usuario = Depends(AVALIADOR_TECNICO),
):
    pdf = await baixar_relatorio_do_meu_projeto(db, avaliador, submissao_id)
    return resposta_relatorio_pdf(pdf)
