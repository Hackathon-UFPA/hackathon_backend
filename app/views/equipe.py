from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.composicao import ComposicaoResponse
from app.schemas.equipe import ComposicaoUpdate, EquipeCreate, EquipeResponse, EquipeUpdate
from app.security.dependencias import exigir_papeis, usuario_ativo
from app.services import composicao
from app.services.equipe import consultar, criar, editar, listar_minhas
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/equipes", tags=["Equipes"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"


@router.post(
    "",
    response_model=EquipeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar equipe",
    description=(
        "Cria a equipe em `EM_FORMACAO` e o vínculo `LIDER` do usuário autenticado na mesma "
        "transação (RF18). Restrito a `PARTICIPANTE`, com a exceção técnica `DEV`. "
        "Exige hackathon existente com `status = INSCRICOES` (RN06) e "
        "nenhum vínculo do usuário nesta edição (RN02). Não exige mínimo de integrantes ou "
        "aceites de termos nesta operação. Aceites têm endpoints próprios. "
        "O líder é definido pelo sistema. Além de `hackathon_id` e `nome`, aceita (BE-S5-01, "
        "decisão de 05/11) `categoria` (ESTUDANTES, PROFISSIONAIS ou MISTA; omitida, ESTUDANTES), "
        "`tipo_lider` e `integrantes`: a composição completa (nome, e-mail e `tipo_integrante` "
        "de cada pessoa, sem o líder). Com `integrantes`, o total precisa estar entre "
        "`min_integrantes` e `max_integrantes` da edição (RN01), a categoria precisa ser aceita "
        "pela edição, os tipos precisam formar a categoria (MISTA: ao menos um ESTUDANTE e um "
        "PROFISSIONAL) e os convites saem na mesma transação; qualquer falha não grava nada (422). "
        "Dados pessoais, aceite de termos e comprovante são de cada pessoa e não são aceitos "
        "aqui. As pendências individuais ficam em `GET /equipes/{id}/composicao`."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Hackathon não encontrado",
            409: "Inscrições fechadas ou usuário já participa de equipe nesta edição",
            422: "Composição inválida: limites, e-mail repetido, categoria não aceita ou tipos "
            "incoerentes",
        }
    ),
)
async def criar_uma_equipe(
    dados: EquipeCreate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(exigir_papeis(PapelUsuario.PARTICIPANTE)),
):
    return await criar(db, usuario, dados)


# A rota fixa precisa ser registrada antes de /{equipe_id}.
@router.get(
    "/minhas",
    response_model=list[EquipeResponse],
    summary="Minhas equipes",
    description=(
        "Lista apenas as equipes das quais o usuário autenticado é integrante, em todas as "
        "edições, inclusive para DEV. Não inclui dados de usuários ou convites."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403}),
)
async def minhas_equipes(
    db: AsyncSession = Depends(get_session), usuario: Usuario = Depends(usuario_ativo)
):
    return await listar_minhas(db, usuario)


@router.get(
    "/{equipe_id}",
    response_model=EquipeResponse,
    summary="Consultar equipe",
    description="Consulta restrita a integrantes da equipe, com a exceção técnica DEV.",
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Equipe não encontrada"}),
)
async def consultar_equipe(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await consultar(db, usuario, equipe_id)


@router.patch(
    "/{equipe_id}",
    response_model=EquipeResponse,
    summary="Editar nome da equipe",
    description=(
        "O líder técnico pode editar apenas `nome` (RF24, RN03), com a exceção técnica DEV. "
        "Exige equipe em `EM_FORMACAO` e hackathon com `status = INSCRICOES` (RN06). "
        "Campos adicionais, como situação, datas e hackathon, são rejeitados."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Equipe não encontrada",
            409: "Inscrições fechadas ou equipe fora de EM_FORMACAO",
        }
    ),
)
async def editar_equipe(
    equipe_id: UUID,
    dados: EquipeUpdate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await editar(db, usuario, equipe_id, dados)


@router.get(
    "/{equipe_id}/composicao",
    response_model=ComposicaoResponse,
    summary="Consultar a composição da equipe",
    description=(
        "Para cada pessoa, separa o que o líder indicou (nome, e-mail, tipo) do que ela já "
        "confirmou com a própria conta (convite, conta ativa, termos e comprovante), e traz as "
        "pendências individuais e as da equipe. Convites em aberto não revelam se o e-mail tem "
        "conta. Restrito a integrantes, com a exceção técnica DEV."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Equipe não encontrada"}),
)
async def consultar_composicao(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await composicao.consultar(db, usuario, equipe_id)


@router.put(
    "/{equipe_id}/composicao",
    response_model=ComposicaoResponse,
    summary="Substituir a composição da equipe",
    description=(
        "O líder (RN03, DEV como exceção) informa de novo a categoria e a composição inteira "
        "(RF24). Quem não está na lista é retirado e avisado; convites em aberto de quem saiu "
        "são cancelados; quem é novo recebe convite. Tudo na mesma transação, com a equipe "
        "travada contra aceites simultâneos. Exige equipe em `EM_FORMACAO` e inscrições abertas "
        "(RN06). Valem as mesmas regras de limites, categoria, tipos e e-mails do POST. Quem "
        "aceitou, saiu e é incluído de novo recebe 409: o reconvite à mesma equipe ainda não "
        "está disponível. Termos e comprovantes continuam sendo de cada pessoa."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403,
            404: "Equipe não encontrada",
            409: "Inscrições fechadas, equipe fora de EM_FORMACAO ou reconvite indisponível",
            422: "Composição inválida: limites, e-mail repetido, categoria não aceita ou tipos "
            "incoerentes",
        }
    ),
)
async def substituir_composicao(
    equipe_id: UUID,
    dados: ComposicaoUpdate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await composicao.editar(db, usuario, equipe_id, dados)
