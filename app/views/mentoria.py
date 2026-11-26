from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.mentoria import (
    EntregaMentoriaCreate,
    EntregaMentoriaResponse,
    MarcoMentoriaCreate,
    MarcoMentoriaResponse,
    MarcoMentoriaUpdate,
    SubmissaoFinalResponse,
    UrlRepositorio,
)
from app.security.dependencias import usuario_ativo
from app.security.organizacao import gestor_do_hackathon
from app.services import mentoria as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(
    tags=["Entregas da mentoria"],
    responses=respostas_de_erro(
        {
            401: "JWT ausente, inválido ou conta desativada.",
            403: "Conta pendente, perfil sem permissão ou recurso fora do escopo do usuário.",
        }
    ),
)

MarcosAdmin = "/admin/hackathons/{hackathon_id}/mentoria/marcos"
MarcosEdicao = "/hackathons/{hackathon_id}/mentoria/marcos"
EntregasEquipe = "/equipes/{equipe_id}/mentoria/entregas"
SubmissaoFinalEquipe = "/equipes/{equipe_id}/mentoria/submissao-final"
RelatorioPDF = {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}
Db = Annotated[AsyncSession, Depends(get_session)]
Gestor = Annotated[Usuario, Depends(gestor_do_hackathon(*service.GESTORES_MENTORIA))]
UsuarioAtivo = Annotated[Usuario, Depends(usuario_ativo)]
Limite = Annotated[int, Query(ge=1, le=100)]
Deslocamento = Annotated[int, Query(ge=0)]


@router.post(
    MarcosAdmin,
    response_model=MarcoMentoriaResponse,
    status_code=status.HTTP_201_CREATED,
    responses=respostas_de_erro(
        {
            404: "Edição inexistente.",
            409: "Edição encerrada, prazo incompatível ou conflito com o marco final.",
        }
    ),
)
async def criar_marco(hackathon_id: UUID, dados: MarcoMentoriaCreate, db: Db, gestor: Gestor):
    """Comitê Científico ou Organizador da organização proprietária, e DEV.

    Cadastra um marco comum às equipes da edição. O tipo FINAL reserva a última posição.
    """
    return await service.criar_marco(db, hackathon_id, dados)


@router.get(
    MarcosAdmin,
    response_model=list[MarcoMentoriaResponse],
    responses=respostas_de_erro({404: "Edição inexistente."}),
)
async def listar_marcos_admin(
    hackathon_id: UUID, db: Db, gestor: Gestor, limite: Limite = 50, deslocamento: Deslocamento = 0
):
    """Comitê Científico ou Organizador da organização proprietária, e DEV.

    Lista os marcos da edição por prazo crescente e, em caso de empate, pela ordem configurada.
    """
    return await service.listar_marcos(db, gestor, hackathon_id, limite, deslocamento)


@router.get(
    MarcosAdmin + "/{marco_id}",
    response_model=MarcoMentoriaResponse,
    responses=respostas_de_erro({404: "Edição inexistente ou marco ausente na edição."}),
)
async def consultar_marco_admin(hackathon_id: UUID, marco_id: UUID, db: Db, gestor: Gestor):
    """Comitê Científico ou Organizador da organização proprietária, e DEV."""
    return await service.consultar_marco(db, hackathon_id, marco_id)


@router.patch(
    MarcosAdmin + "/{marco_id}",
    response_model=MarcoMentoriaResponse,
    responses=respostas_de_erro(
        {
            404: "Edição inexistente ou marco ausente na edição.",
            409: (
                "Edição finalizada ou cancelada, calendário incompatível, "
                "mudança de tipo ou antecipação de prazo em marco com entregas."
            ),
        }
    ),
)
async def editar_marco(
    hackathon_id: UUID, marco_id: UUID, dados: MarcoMentoriaUpdate, db: Db, gestor: Gestor
):
    """Comitê Científico ou Organizador da organização proprietária, e DEV.

    Edita os campos informados. Entregas registradas conservam o prazo vigente no envio.
    """
    return await service.editar_marco(db, hackathon_id, marco_id, dados)


@router.delete(
    MarcosAdmin + "/{marco_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=respostas_de_erro(
        {
            404: "Edição inexistente ou marco ausente na edição.",
            409: "Edição finalizada ou cancelada, ou marco com histórico de entregas.",
        }
    ),
)
async def excluir_marco(hackathon_id: UUID, marco_id: UUID, db: Db, gestor: Gestor) -> Response:
    """Comitê Científico ou Organizador da organização proprietária, e DEV.

    Exclui um marco sem entregas vinculadas.
    """
    await service.excluir_marco(db, hackathon_id, marco_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    MarcosEdicao,
    response_model=list[MarcoMentoriaResponse],
    responses=respostas_de_erro({404: "Edição inexistente ou rascunho privado."}),
)
async def listar_marcos(
    hackathon_id: UUID,
    db: Db,
    usuario: UsuarioAtivo,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
):
    """Integrantes de equipe homologada com proposta aprovada e mentores com atribuição vigente.

    Também disponível ao Comitê Científico e Organizador da organização proprietária, e DEV.
    """
    return await service.listar_marcos(db, usuario, hackathon_id, limite, deslocamento)


@router.post(
    EntregasEquipe,
    response_model=EntregaMentoriaResponse,
    status_code=status.HTTP_201_CREATED,
    responses=respostas_de_erro(
        {
            404: "Equipe ou edição inexistente, ou marco ausente na edição da equipe.",
            409: "Equipe inelegível, período indisponível, marco final ou entrega duplicada.",
        }
    ),
)
async def registrar_entrega(
    equipe_id: UUID, dados: EntregaMentoriaCreate, db: Db, usuario: UsuarioAtivo
):
    """Líder técnico da equipe ou DEV. Um envio por equipe e marco parcial.

    Exige treinamento concluído, equipe homologada, proposta aprovada e prazo vigente.
    A API registra a autoria do usuário autenticado, o instante e o prazo do envio em UTC.
    """
    return await service.registrar_entrega(db, usuario, equipe_id, dados)


@router.get(
    EntregasEquipe,
    response_model=list[EntregaMentoriaResponse],
    responses=respostas_de_erro({404: "Equipe ou edição inexistente ou rascunho privado."}),
)
async def listar_entregas(
    equipe_id: UUID,
    db: Db,
    usuario: UsuarioAtivo,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
):
    """Integrantes da equipe, mentor vigente, gestores da organização proprietária e DEV.

    Lista os envios da equipe a partir do mais recente.
    """
    return await service.listar_entregas(db, usuario, equipe_id, limite, deslocamento)


@router.get(
    EntregasEquipe + "/{entrega_id}",
    response_model=EntregaMentoriaResponse,
    responses=respostas_de_erro(
        {404: "Equipe, edição acessível ou entrega da equipe inexistente."}
    ),
)
async def consultar_entrega(equipe_id: UUID, entrega_id: UUID, db: Db, usuario: UsuarioAtivo):
    """Integrantes da equipe, mentor vigente, gestores da organização proprietária e DEV."""
    return await service.consultar_entrega(db, usuario, equipe_id, entrega_id)


def resposta_relatorio_pdf(pdf: bytes) -> Response:
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="relatorio-final.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    SubmissaoFinalEquipe,
    response_model=SubmissaoFinalResponse,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={"requestBody": {"required": True, "content": RelatorioPDF}},
    responses=respostas_de_erro(
        {
            404: "Equipe, hackathon ou marco final inexistente.",
            409: "Equipe ou edição inelegível, prazo indisponível ou submissão duplicada.",
            413: "PDF com mais de 10 MB.",
            415: "Content-Type diferente de application/pdf.",
            422: "Link inválido, repositório inacessível ou PDF ilegível.",
            503: "Falha temporária ao validar o repositório no GitHub.",
        }
    ),
)
async def registrar_submissao_final(
    equipe_id: UUID,
    request: Request,
    db: Db,
    usuario: UsuarioAtivo,
    repositorio_url: Annotated[
        UrlRepositorio,
        Query(description="URL HTTPS do repositório GitHub público, no formato dono/repositório."),
    ],
):
    """Líder técnico ou DEV. Envia os bytes do relatório (PDF de até 10 MB) no corpo.

    O envio usa o marco FINAL da edição e exige equipe homologada, proposta aprovada
    no resultado homologado, treinamento concluído e período aberto.
    """
    return await service.registrar_submissao_final(
        db,
        usuario,
        equipe_id,
        repositorio_url,
        request.stream(),
        request.headers.get("content-type", ""),
    )


@router.get(
    SubmissaoFinalEquipe,
    response_model=SubmissaoFinalResponse,
    responses=respostas_de_erro({404: "Equipe, edição acessível ou submissão final inexistente."}),
)
async def consultar_submissao_final(equipe_id: UUID, db: Db, usuario: UsuarioAtivo):
    """Integrantes da equipe, mentor vigente, gestores da organização proprietária e DEV.

    Consulta os artefatos, a autoria, o horário e o prazo do envio, inclusive após o encerramento.
    """
    return await service.consultar_submissao_final(db, usuario, equipe_id)


@router.get(
    SubmissaoFinalEquipe + "/relatorio",
    response_class=Response,
    responses={
        200: {"description": "PDF do relatório final", "content": RelatorioPDF},
        **respostas_de_erro({404: "Equipe, edição acessível ou relatório final inexistente."}),
    },
)
async def baixar_relatorio_final(equipe_id: UUID, db: Db, usuario: UsuarioAtivo):
    """Baixa o PDF com as mesmas permissões da consulta da submissão final da equipe."""
    pdf = await service.baixar_relatorio_final(db, usuario, equipe_id)
    return resposta_relatorio_pdf(pdf)
