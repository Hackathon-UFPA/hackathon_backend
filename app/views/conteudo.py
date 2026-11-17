"""Conteúdo institucional da edição (BE-S5-12): rotas administrativas de apoiadores, FAQ e
cronograma, e a página pública (RF10 a RF14). O regulamento e o treinamento têm rotas próprias
(`regulamento.py` e `treinamento.py`)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.conteudo import (
    ApoiadorCreate,
    ApoiadoresPorCategoria,
    ApoiadorResponse,
    ApoiadorUpdate,
    FaqCreate,
    FaqOrdem,
    FaqPublico,
    FaqResponse,
    FaqUpdate,
    FaseCreate,
    FaseCronogramaResponse,
    FaseUpdate,
    HackathonPublico,
    PaginaPublicaResponse,
    RegulamentoPublico,
)
from app.security.organizacao import gestor_do_hackathon
from app.security.permissoes import PERFIS_QUE_GERENCIAM_EDITAL
from app.services import conteudo as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/admin/hackathons/{hackathon_id}", tags=["Conteúdo institucional"])
router_publico = APIRouter(prefix="/publico/hackathons", tags=["Página pública"])

# Só o Organizador da organização dona do hackathon (e DEV)
gerencia_conteudo = gestor_do_hackathon(*PERFIS_QUE_GERENCIAM_EDITAL)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão (só Organizador e DEV)"
ERRO_404_EDICAO = "Hackathon não encontrado"
ERROS = {401: ERRO_401, 403: ERRO_403, 404: ERRO_404_EDICAO}
ERRO_404_PUBLICO = "Hackathon não encontrado, ou ainda em rascunho (não divulgado)"


def _pagina(limite: int = Query(default=50, ge=1, le=100), deslocamento: int = Query(0, ge=0)):
    return limite, deslocamento


# --- Apoiadores (RF14) ---


@router.post(
    "/apoiadores",
    response_model=ApoiadorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar apoiador",
    description=(
        "Somente Organizador ou DEV (RF14). Realizadores, apoiadores e patrocinadores da "
        "edição, com `nome`, `categoria`, `logo_url` e `site_url`. **Só links**, nunca arquivo "
        "(RNF20): `https`, e o logo precisa ser uma imagem (png, jpg, jpeg, webp ou svg). Nasce "
        "**não publicado**; vai para o fim da lista."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Campo inválido ou link fora da política"}),
)
async def criar_apoiador(
    hackathon_id: UUID,
    dados: ApoiadorCreate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    return await service.criar_apoiador(db, hackathon_id, dados)


@router.get(
    "/apoiadores",
    response_model=list[ApoiadorResponse],
    summary="Listar apoiadores (administração)",
    description=(
        "Somente Organizador ou DEV. Publicados e não publicados, na ordem de exibição. Filtros "
        "`publicado` e `categoria`; paginação por `limite` (1 a 100) e `deslocamento`."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Parâmetro inválido"}),
)
async def listar_apoiadores(
    hackathon_id: UUID,
    publicado: bool | None = None,
    categoria: str | None = Query(default=None, max_length=80),
    pagina: tuple[int, int] = Depends(_pagina),
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    return await service.listar_apoiadores(
        db,
        hackathon_id,
        publicado=publicado,
        categoria=categoria,
        limite=pagina[0],
        deslocamento=pagina[1],
    )


@router.patch(
    "/apoiadores/{apoiador_id}",
    response_model=ApoiadorResponse,
    summary="Editar apoiador",
    description=(
        "Somente Organizador ou DEV. Altera só o que foi enviado; `logo_url` e `site_url` aceitam "
        "`null` para limpar. `publicado` publica ou retira da página pública e `ordem` muda a "
        "posição."
    ),
    responses=respostas_de_erro(
        {**ERROS, 404: "Hackathon ou apoiador não encontrado", 422: "Campo inválido"}
    ),
)
async def editar_apoiador(
    hackathon_id: UUID,
    apoiador_id: UUID,
    dados: ApoiadorUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    return await service.editar_apoiador(db, hackathon_id, apoiador_id, dados)


@router.delete(
    "/apoiadores/{apoiador_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Excluir apoiador",
    description="Somente Organizador ou DEV. Para só esconder, use `publicado = false`.",
    responses=respostas_de_erro({**ERROS, 404: "Hackathon ou apoiador não encontrado"}),
)
async def excluir_apoiador(
    hackathon_id: UUID,
    apoiador_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    await service.excluir_apoiador(db, hackathon_id, apoiador_id)


# --- FAQ (RF12) ---


@router.post(
    "/faq",
    response_model=FaqResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar pergunta frequente",
    description=(
        "Somente Organizador ou DEV (RF12). Nasce **não publicada**, no fim da lista. Criações "
        "simultâneas recebem posições distintas."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Campo inválido"}),
)
async def criar_faq(
    hackathon_id: UUID,
    dados: FaqCreate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    return await service.criar_faq(db, hackathon_id, dados)


@router.get(
    "/faq",
    response_model=list[FaqResponse],
    summary="Listar perguntas frequentes (administração)",
    description=(
        "Somente Organizador ou DEV. Publicadas e não publicadas, na ordem de exibição. Filtro "
        "`publicado`; paginação por `limite` (1 a 100) e `deslocamento`."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Parâmetro inválido"}),
)
async def listar_faq(
    hackathon_id: UUID,
    publicado: bool | None = None,
    pagina: tuple[int, int] = Depends(_pagina),
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    return await service.listar_faq(
        db, hackathon_id, publicado=publicado, limite=pagina[0], deslocamento=pagina[1]
    )


@router.put(
    "/faq/ordem",
    response_model=list[FaqResponse],
    summary="Reordenar as perguntas",
    description=(
        "Somente Organizador ou DEV. Envie **todos** os ids da edição na nova ordem. Se a lista "
        "não for exatamente o conjunto atual (alguém criou ou excluiu uma pergunta no meio do "
        "caminho), responde 409: recarregue a lista e tente de novo. Reordenações simultâneas se "
        "enfileiram e a última vale."
    ),
    responses=respostas_de_erro(
        {**ERROS, 409: "A lista não corresponde às perguntas atuais", 422: "Ids repetidos"}
    ),
)
async def reordenar_faq(
    hackathon_id: UUID,
    dados: FaqOrdem,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    return await service.reordenar_faq(db, hackathon_id, dados.ids)


@router.patch(
    "/faq/{item_id}",
    response_model=FaqResponse,
    summary="Editar pergunta frequente",
    description="Somente Organizador ou DEV. Altera só o que foi enviado, inclusive `publicado`.",
    responses=respostas_de_erro(
        {**ERROS, 404: "Hackathon ou pergunta não encontrada", 422: "Campo inválido"}
    ),
)
async def editar_faq(
    hackathon_id: UUID,
    item_id: UUID,
    dados: FaqUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    return await service.editar_faq(db, hackathon_id, item_id, dados)


@router.delete(
    "/faq/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Excluir pergunta frequente",
    description="Somente Organizador ou DEV. Para só esconder, use `publicado = false`.",
    responses=respostas_de_erro({**ERROS, 404: "Hackathon ou pergunta não encontrada"}),
)
async def excluir_faq(
    hackathon_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    await service.excluir_faq(db, hackathon_id, item_id)


# --- Cronograma (RF13, RF59) ---


@router.get(
    "/cronograma",
    response_model=list[FaseCronogramaResponse],
    summary="Cronograma da edição (administração)",
    description=(
        "Somente Organizador ou DEV (RF13, RF59). Em ordem cronológica: as datas do próprio "
        "edital (`origem = EDITAL`: inscrições, homologação, propostas e evento, lidas de "
        "`hackathon`, sem `id`) e as fases cadastradas aqui (`PERSONALIZADA`), publicadas ou "
        "não. Cada linha traz a `situacao` (NAO_INICIADA, EM_ANDAMENTO, ENCERRADA) e `atual`. "
        "Abrir, encerrar e reabrir fases do edital, com auditoria, é a BE-S7-05."
    ),
    responses=respostas_de_erro(ERROS),
)
async def cronograma_admin(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    return await service.cronograma_admin(db, hackathon_id)


@router.post(
    "/cronograma",
    response_model=FaseCronogramaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar fase do cronograma",
    description=(
        "Somente Organizador ou DEV (RF13). Fase extra com `nome`, `inicio` e `fim` (UTC; data "
        "sem fuso vale como UTC); `fim` não pode ser antes de `inicio`. Nasce **não publicada**. "
        "As datas do edital não se cadastram aqui: elas vêm de `PATCH /admin/hackathons/{id}`."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Campo inválido ou período fora de ordem"}),
)
async def criar_fase(
    hackathon_id: UUID,
    dados: FaseCreate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    fase = await service.criar_fase(db, hackathon_id, dados)
    return await _linha_da_fase(db, hackathon_id, fase.id)


@router.patch(
    "/cronograma/{fase_id}",
    response_model=FaseCronogramaResponse,
    summary="Editar fase do cronograma",
    description=(
        "Somente Organizador ou DEV. Altera só o que foi enviado; o período final é validado "
        "com os valores já gravados."
    ),
    responses=respostas_de_erro(
        {**ERROS, 404: "Hackathon ou fase não encontrada", 422: "Campo ou período inválido"}
    ),
)
async def editar_fase(
    hackathon_id: UUID,
    fase_id: UUID,
    dados: FaseUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    await service.editar_fase(db, hackathon_id, fase_id, dados)
    return await _linha_da_fase(db, hackathon_id, fase_id)


@router.delete(
    "/cronograma/{fase_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Excluir fase do cronograma",
    description="Somente Organizador ou DEV.",
    responses=respostas_de_erro({**ERROS, 404: "Hackathon ou fase não encontrada"}),
)
async def excluir_fase(
    hackathon_id: UUID,
    fase_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_conteudo),
):
    await service.excluir_fase(db, hackathon_id, fase_id)


async def _linha_da_fase(db: AsyncSession, hackathon_id: UUID, fase_id: UUID):
    linhas = await service.cronograma_admin(db, hackathon_id)
    return next(linha for linha in linhas if linha.id == fase_id)


# --- Página pública (RF10 a RF14), sem login ---


@router_publico.get(
    "",
    response_model=list[HackathonPublico],
    summary="Edições divulgadas (público)",
    description=(
        "**Não exige login** (RF10). Todas as edições, menos as em `RASCUNHO`, das mais recentes "
        "às mais antigas. `inscricoes_abertas` segue a RN06. Paginação por `limite` (1 a 100) e "
        "`deslocamento`."
    ),
    responses=respostas_de_erro({422: "Parâmetro inválido"}),
)
async def listar_edicoes(
    pagina: tuple[int, int] = Depends(_pagina), db: AsyncSession = Depends(get_session)
):
    return await service.listar_edicoes_publicas(db, pagina[0], pagina[1])


@router_publico.get(
    "/{hackathon_id}",
    response_model=PaginaPublicaResponse,
    summary="Página pública da edição",
    description=(
        "**Não exige login** (RF10 a RF14). Nome, tema, descrição, datas e `inscricoes_abertas`, "
        "mais o regulamento vigente (com a data da última atualização), as perguntas "
        "publicadas em ordem, o cronograma cronológico com a fase atual destacada e os "
        "apoiadores publicados agrupados por categoria. Só conteúdo **publicado** aparece. "
        "Edição em rascunho responde 404."
    ),
    responses=respostas_de_erro({404: ERRO_404_PUBLICO}),
)
async def pagina_publica(hackathon_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.pagina_publica(db, hackathon_id)


@router_publico.get(
    "/{hackathon_id}/regulamento",
    response_model=RegulamentoPublico,
    summary="Regulamento vigente (público)",
    description=(
        "**Não exige login** (RF11). Só a versão publicada; `publicado_em` é a data da última "
        "atualização. Sem versão publicada, 404."
    ),
    responses=respostas_de_erro({404: "Edição em rascunho, ou sem regulamento publicado"}),
)
async def regulamento(hackathon_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.regulamento_publico(db, hackathon_id)


@router_publico.get(
    "/{hackathon_id}/faq",
    response_model=list[FaqPublico],
    summary="Perguntas frequentes publicadas (público)",
    description="**Não exige login** (RF12). Só as publicadas, na ordem definida pela organização.",
    responses=respostas_de_erro({404: ERRO_404_PUBLICO}),
)
async def faq(hackathon_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.faq_publico(db, hackathon_id)


@router_publico.get(
    "/{hackathon_id}/cronograma",
    response_model=list[FaseCronogramaResponse],
    summary="Cronograma (público)",
    description=(
        "**Não exige login** (RF13). Datas do edital e fases publicadas, em ordem cronológica; "
        "a fase em andamento vem com `atual = true`."
    ),
    responses=respostas_de_erro({404: ERRO_404_PUBLICO}),
)
async def cronograma(hackathon_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.cronograma_publico(db, hackathon_id)


@router_publico.get(
    "/{hackathon_id}/apoiadores",
    response_model=list[ApoiadoresPorCategoria],
    summary="Apoiadores e patrocinadores (público)",
    description=(
        "**Não exige login** (RF14). Só os publicados, agrupados por categoria; cada um traz "
        "`nome`, `logo_url` e `site_url` (o logo abre o site)."
    ),
    responses=respostas_de_erro({404: ERRO_404_PUBLICO}),
)
async def apoiadores(hackathon_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.apoiadores_publicos(db, hackathon_id)
