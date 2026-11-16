from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoTermo
from app.db.db import get_session
from app.models import Usuario
from app.schemas.conteudo import TermoAdminResponse, TermoRascunhoCreate, TermoRascunhoUpdate
from app.security.dependencias import exigir_papeis
from app.security.permissoes import PERFIS_QUE_GERENCIAM_EDITAL
from app.services import regulamento as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(
    prefix="/admin/hackathons/{hackathon_id}/termos", tags=["Regulamento e termos (admin)"]
)

gerencia_regulamento = exigir_papeis(*PERFIS_QUE_GERENCIAM_EDITAL)

ERROS = {
    401: "Sem token, ou token inválido, vencido ou de conta desativada",
    403: "Conta pendente, ou quem pede não tem permissão (só Organizador e DEV)",
    404: "Hackathon ou versão não encontrada",
}
ERRO_409_PUBLICADA = "A versão já foi publicada e não muda mais (RN05)"


@router.post(
    "",
    response_model=TermoAdminResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar versão do regulamento ou do termo (rascunho)",
    description=(
        "Somente Organizador ou DEV (RF11). Cria uma versão em **rascunho**: editável, "
        "excluível e invisível ao público. Informe `conteudo` (texto) ou `url` (link `https` do "
        "PDF, RNF20), ou os dois. `tipo` é `REGULAMENTO` (padrão) ou `TERMO_CONSENTIMENTO`; o "
        "número da `versao` é único por tipo na edição. Para publicar, use `POST .../publicar`."
    ),
    responses=respostas_de_erro(
        {
            **ERROS,
            409: "Já existe uma versão com este número para este tipo",
            422: "Faltou conteudo ou url, ou link fora da política",
        }
    ),
)
async def criar_versao(
    hackathon_id: UUID,
    dados: TermoRascunhoCreate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_regulamento),
):
    return await service.criar_rascunho(db, hackathon_id, dados)


@router.get(
    "",
    response_model=list[TermoAdminResponse],
    summary="Listar versões do regulamento e dos termos",
    description=(
        "Somente Organizador ou DEV. Todas as versões (rascunhos, a vigente e as antigas), por "
        "tipo e da mais recente para a mais antiga. Filtros `tipo` e `rascunho`; paginação por "
        "`limite` (1 a 100) e `deslocamento`."
    ),
    responses=respostas_de_erro({**ERROS, 422: "Parâmetro inválido"}),
)
async def listar_versoes(
    hackathon_id: UUID,
    tipo: TipoTermo | None = None,
    rascunho: bool | None = None,
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_regulamento),
):
    return await service.listar(
        db, hackathon_id, tipo=tipo, rascunho=rascunho, limite=limite, deslocamento=deslocamento
    )


@router.patch(
    "/{termo_id}",
    response_model=TermoAdminResponse,
    summary="Editar rascunho",
    description=(
        "Somente Organizador ou DEV. Só rascunhos mudam: `titulo`, `conteudo` e `url` (`null` "
        "limpa um dos dois, mas um precisa ficar). Versão publicada responde 409: crie uma nova."
    ),
    responses=respostas_de_erro(
        {**ERROS, 409: ERRO_409_PUBLICADA, 422: "Campo inválido ou sem conteudo e url"}
    ),
)
async def editar_rascunho(
    hackathon_id: UUID,
    termo_id: UUID,
    dados: TermoRascunhoUpdate,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_regulamento),
):
    return await service.editar_rascunho(db, hackathon_id, termo_id, dados)


@router.delete(
    "/{termo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Excluir rascunho",
    description="Somente Organizador ou DEV. Só rascunhos: uma versão publicada tem aceites.",
    responses=respostas_de_erro({**ERROS, 409: ERRO_409_PUBLICADA}),
)
async def excluir_rascunho(
    hackathon_id: UUID,
    termo_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_regulamento),
):
    await service.excluir_rascunho(db, hackathon_id, termo_id)


@router.post(
    "/{termo_id}/publicar",
    response_model=TermoAdminResponse,
    summary="Publicar versão",
    description=(
        "Somente Organizador ou DEV (RF11). Torna a versão **vigente** e aposenta a vigente "
        "anterior do mesmo tipo, na mesma transação; `publicado_em` registra a data. A partir "
        "daí a versão não muda mais, e quem aceitou a anterior precisa aceitar a nova (RF20, "
        "RN05). Publicar de novo a vigente não muda nada; uma versão já substituída responde 409. "
        "Publicações simultâneas se enfileiram: a última vence e nunca há duas vigentes."
    ),
    responses=respostas_de_erro(
        {**ERROS, 409: "A versão já foi substituída por outra: crie uma nova"}
    ),
)
async def publicar_versao(
    hackathon_id: UUID,
    termo_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: Usuario = Depends(gerencia_regulamento),
):
    return await service.publicar(db, hackathon_id, termo_id)
