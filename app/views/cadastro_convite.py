from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.db import get_session
from app.schemas.cadastro_convite import (
    CadastroPorConviteRequest,
    ConviteCadastroConsulta,
    ConviteCadastroConsultaResponse,
)
from app.schemas.usuario import UsuarioResponse
from app.services import cadastro_convite as service
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/auth/cadastro/convite", tags=["Autenticação"])

ERRO_400 = "Link inexistente, vencido, já usado ou de convite que não vale mais"


@router.post(
    "/consulta",
    response_model=ConviteCadastroConsultaResponse,
    summary="Consultar o convite do link de cadastro",
    description=(
        "Público, sem login (BE-S5-02). Quem abriu o link de cadastro enviado por e-mail confere o "
        "convite (e-mail fixo, nome indicado, equipe e líder) antes de criar o acesso. Não gasta o "
        "token, que vai no corpo e não na URL para não parar em logs de servidor. Link "
        "inexistente, vencido, já usado ou de convite que não vale mais dá sempre o mesmo 400."
    ),
    responses=respostas_de_erro({400: ERRO_400}),
)
async def consultar_convite(
    dados: ConviteCadastroConsulta, db: AsyncSession = Depends(get_session)
):
    return await service.consultar(db, dados.token)


@router.post(
    "",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar-se pelo link do convite",
    description=(
        "Cadastro próprio de quem foi convidado para uma equipe sem ter conta (BE-S5-02). O líder "
        "nunca cria conta nem define senha: a pessoa cria o acesso com o e-mail do convite, a "
        "própria senha e, se quiser, o link do comprovante (que também pode ser enviado depois, "
        "em `POST /comprovantes`). O token prova a posse do e-mail, que já nasce confirmado, e é "
        "de uso único: dois usos simultâneos resultam em um 201 e um 400. A conta nasce "
        "**pendente** (RN25) e continua podendo aceitar ou recusar o convite e os termos. "
        "Cadastrar não aceita o convite: isso é feito depois, com a própria conta. Se já existe "
        "conta com o e-mail do convite, 409: a pessoa entra com ela."
    ),
    responses=respostas_de_erro(
        {
            400: ERRO_400,
            409: "Já existe conta com o e-mail do convite",
            422: "Campos inválidos (senha fraca, link de comprovante inválido, campos extras)",
        }
    ),
)
async def cadastrar_por_convite(
    dados: CadastroPorConviteRequest, db: AsyncSession = Depends(get_session)
):
    return await service.cadastrar(db, dados)
