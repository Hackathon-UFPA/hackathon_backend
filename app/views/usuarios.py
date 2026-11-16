from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.models import Usuario
from app.schemas.auth import PerfisCadastraveisResponse, UsuarioAdminCreate
from app.schemas.perfil import UsuarioAdminUpdate
from app.schemas.usuario import UsuarioResponse
from app.security.dependencias import exigir_papeis
from app.security.permissoes import perfis_cadastraveis
from app.services import usuario as servico
from app.services.usuario import cadastrar_usuario_por_perfil
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/admin/usuarios", tags=["Usuários"])

gestor_de_usuarios = exigir_papeis(PapelUsuario.ORGANIZADOR, PapelUsuario.COMITE_CIENTIFICO)

ERRO_401 = "Sem token, ou token inválido, vencido ou de conta desativada"


@router.get(
    "/perfis",
    response_model=PerfisCadastraveisResponse,
    summary="Perfis que posso cadastrar",
    description=(
        "Lista os perfis que o usuário logado pode criar (RF07, RF08), para a interface montar "
        "o formulário de cadastro sem repetir a hierarquia: o Organizador cadastra qualquer "
        "perfil de negócio e o Comitê Científico cadastra Comitê Técnico e Mentor."
    ),
    responses=respostas_de_erro(
        {401: ERRO_401, 403: "Perfil sem permissão para esta rota, ou conta ainda pendente"}
    ),
)
async def listar_perfis_cadastraveis(quem_cadastra: Usuario = Depends(gestor_de_usuarios)):
    return PerfisCadastraveisResponse(perfis=perfis_cadastraveis(quem_cadastra.papel))


@router.post(
    "",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar usuário de outro perfil",
    description=(
        "Cria usuários conforme RF07/RF08. Mentores exigem nome, e-mail, empresa, área e "
        "capacidade, além de hackathon_id para vincular o convite à edição, e seguem RN33: "
        "cadastro inativo, convite por e-mail e senha definida pelo "
        "próprio mentor. Para os demais perfis, exige senha inicial e cria a conta ativa. "
        "Não pede comprovante de vínculo."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: "Perfil sem permissão para esta rota, conta pendente, ou `papel` que quem "
            "cadastra não pode criar",
            409: "E-mail já cadastrado",
            404: "Edição informada para o convite de mentor não encontrada",
        }
    ),
)
async def cadastrar_usuario(
    dados: UsuarioAdminCreate,
    db: AsyncSession = Depends(get_session),
    quem_cadastra: Usuario = Depends(gestor_de_usuarios),
):
    return await cadastrar_usuario_por_perfil(db, quem_cadastra, dados)


ERRO_403_GESTAO = (
    "Perfil sem permissão para esta rota, conta pendente, ou usuário de um perfil fora do "
    "alcance de quem gerencia (RN24)"
)


@router.get(
    "",
    response_model=list[UsuarioResponse],
    summary="Listar usuários que posso gerenciar",
    description=(
        "RN24. Só aparecem os perfis que o usuário logado pode gerenciar: o Organizador vê todos "
        "menos DEV; o Comitê Científico, Comitê Técnico e Mentor. Filtros por `papel`, `ativo` e "
        "`busca` (parte do nome ou do e-mail); paginação por `limite` e `deslocamento`."
    ),
    responses=respostas_de_erro({401: ERRO_401, 403: ERRO_403_GESTAO}),
)
async def listar_usuarios(
    papel: PapelUsuario | None = None,
    ativo: bool | None = None,
    busca: str | None = Query(default=None, max_length=100),
    limite: int = Query(default=50, ge=1, le=100),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    quem_gerencia: Usuario = Depends(gestor_de_usuarios),
):
    return await servico.listar(
        db,
        quem_gerencia,
        papel=papel,
        ativo=ativo,
        busca=busca,
        limite=limite,
        deslocamento=deslocamento,
    )


@router.get(
    "/{usuario_id}",
    response_model=UsuarioResponse,
    summary="Consultar um usuário",
    responses=respostas_de_erro(
        {401: ERRO_401, 403: ERRO_403_GESTAO, 404: "Usuário não encontrado"}
    ),
)
async def consultar_usuario(
    usuario_id: UUID,
    db: AsyncSession = Depends(get_session),
    quem_gerencia: Usuario = Depends(gestor_de_usuarios),
):
    return await servico.consultar(db, quem_gerencia, usuario_id)


@router.patch(
    "/{usuario_id}",
    response_model=UsuarioResponse,
    summary="Editar um usuário",
    description=(
        "RN24. Altera nome, instituição, curso, período e, só entre Comitê Técnico, Comitê "
        "Científico e Organizador, o perfil. Ninguém entrega um perfil acima do próprio alcance "
        "(403), nem altera o próprio perfil (409), nem deixa o sistema sem Organizador ativo "
        "(409). O e-mail é trocado pelo próprio dono, com confirmação. Mentores seguem as rotas "
        "de `/admin/mentores` (409)."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403_GESTAO,
            404: "Usuário não encontrado",
            409: "Troca de perfil não permitida, alteração do próprio perfil, último Organizador "
            "ativo ou usuário Mentor",
            422: "Campo desconhecido, nulo ou inválido (`ativo` e `situacao_conta` não entram "
            "aqui: use desativar e reativar)",
        }
    ),
)
async def editar_usuario(
    usuario_id: UUID,
    dados: UsuarioAdminUpdate,
    db: AsyncSession = Depends(get_session),
    quem_gerencia: Usuario = Depends(gestor_de_usuarios),
):
    return await servico.atualizar(db, quem_gerencia, usuario_id, dados)


@router.post(
    "/{usuario_id}/desativar",
    response_model=UsuarioResponse,
    summary="Desativar um usuário",
    description=(
        "RN24. Bloqueia o acesso na hora (o token da pessoa passa a dar 401), encerra as sessões "
        "e gasta os links de redefinição e de confirmação pendentes. O histórico é preservado. "
        "Repetir a chamada não muda nada. Não vale para a própria conta, para o último "
        "Organizador ativo nem para Mentores (`/admin/mentores/{id}/desativar`)."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403_GESTAO,
            404: "Usuário não encontrado",
            409: "Própria conta, último Organizador ativo ou usuário Mentor",
        }
    ),
)
async def desativar_usuario(
    usuario_id: UUID,
    db: AsyncSession = Depends(get_session),
    quem_gerencia: Usuario = Depends(gestor_de_usuarios),
):
    return await servico.desativar(db, quem_gerencia, usuario_id)


@router.post(
    "/{usuario_id}/reativar",
    response_model=UsuarioResponse,
    summary="Reativar um usuário",
    description=(
        "RN24. Devolve o acesso a uma conta desativada; a pessoa entra de novo com a senha que já "
        "tinha. Repetir a chamada não muda nada. Mentores usam `/admin/mentores/{id}/ativar`, "
        "que confere os termos da edição (RN33)."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_403_GESTAO,
            404: "Usuário não encontrado",
            409: "Usuário Mentor",
        }
    ),
)
async def reativar_usuario(
    usuario_id: UUID,
    db: AsyncSession = Depends(get_session),
    quem_gerencia: Usuario = Depends(gestor_de_usuarios),
):
    return await servico.reativar(db, quem_gerencia, usuario_id)
