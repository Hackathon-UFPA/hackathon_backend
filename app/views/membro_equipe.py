from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.models import Usuario
from app.schemas.membro_equipe import MembroEquipeResponse, MembroEquipeUpdate
from app.security.dependencias import usuario_ativo
from app.services.membro_equipe import editar, listar, remover
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/equipes/{equipe_id}/membros", tags=["Equipes"])

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"
ERRO_403 = "Conta pendente, ou quem pede não tem permissão para esta rota"
ERRO_404 = "Equipe ou membro não encontrado nesta equipe"
ERRO_409 = "Inscrições fechadas, equipe fora de EM_FORMACAO ou alteração de liderança"


@router.get(
    "",
    response_model=list[MembroEquipeResponse],
    summary="Listar membros da equipe",
    description=(
        "Lista os vínculos e funções dos integrantes. Somente integrantes da equipe ou DEV "
        "podem consultar. A consulta é permitida também após as inscrições. Não inclui dados "
        "privados da conta, como senha, comprovantes ou aceites de termos."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: "Equipe não encontrada"}),
)
async def membros_da_equipe(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await listar(db, usuario, equipe_id)


@router.patch(
    "/{usuario_id}",
    response_model=MembroEquipeResponse,
    summary="Alterar função do membro",
    description=(
        "Somente o líder da equipe ou DEV pode alterar `funcao` (RF24). Exige hackathon em "
        "`INSCRICOES` e equipe em `EM_FORMACAO`. Aceita as funções existentes ou `null` para "
        "deixar sem função. Não permite rebaixar o líder nem promover outro membro a `LIDER`, "
        "inclusive para DEV. Reenviar a mesma função ou corpo vazio preserva os dados. "
        "O membro precisa pertencer à equipe indicada; campos adicionais são rejeitados. "
        "Esta operação não adiciona integrantes nem altera o tamanho da equipe."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: ERRO_404, 409: ERRO_409}),
)
async def editar_funcao(
    equipe_id: UUID,
    usuario_id: UUID,
    dados: MembroEquipeUpdate,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    return await editar(db, usuario, equipe_id, usuario_id, dados)


@router.delete(
    "/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remover integrante da equipe",
    description=(
        "Somente o líder da equipe ou DEV pode remover outro integrante (RF24). Exige "
        "hackathon em `INSCRICOES` e equipe em `EM_FORMACAO`. O líder é protegido, inclusive "
        "contra remoção por DEV. Não exige mínimo de integrantes durante a formação. "
        "Remove apenas o vínculo: preserva convites aceitos e aceites de termos. Um convite "
        "`ACEITO` anterior continua impedindo reconvite ao mesmo e-mail na mesma equipe "
        "(409 no envio), pelo índice atual. O aviso ao removido está pendente de "
        "infraestrutura de notificações; nenhum aviso é enviado nesta versão."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403, 404: ERRO_404, 409: ERRO_409}),
)
async def remover_integrante(
    equipe_id: UUID,
    usuario_id: UUID,
    db: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(usuario_ativo),
):
    await remover(db, usuario, equipe_id, usuario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
