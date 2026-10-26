from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.db.db import get_session
from app.models import Usuario
from app.schemas.auth import CadastroRequest, LoginRequest, TokenResponse
from app.schemas.usuario import UsuarioResponse
from app.security.dependencias import usuario_atual
from app.security.token import criar_token
from app.services.auth import autenticar, cadastrar_participante
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/cadastro",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar participante",
    description=(
        "Cadastro público (RF01), sem login. Cria sempre um **Participante** com a conta "
        "**pendente** e registra o comprovante de vínculo no hackathon com inscrições abertas. "
        "A conta só fica ativa quando o Comitê Científico aprovar o comprovante."
    ),
    responses=respostas_de_erro(
        {409: "E-mail já cadastrado, ou nenhum hackathon com inscrições abertas no momento"}
    ),
)
async def cadastrar(dados: CadastroRequest, db: AsyncSession = Depends(get_session)):
    return await cadastrar_participante(db, dados)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Entrar com e-mail e senha",
    description=(
        "Devolve o token de acesso e os dados do usuário (RF02): a interface escolhe o painel "
        "pelo `papel` e avisa quando `situacao_conta` é `PENDENTE`. O token vale o tempo de "
        "`expires_in` e não é renovado; vencido, é preciso entrar de novo. Depois de 5 senhas "
        "erradas seguidas a conta fica bloqueada por 15 minutos."
    ),
    responses=respostas_de_erro(
        {
            401: "E-mail ou senha inválidos. A mensagem é sempre a mesma, para não dizer qual "
            "dado está errado",
            429: "Conta bloqueada por tentativas erradas. O cabeçalho Retry-After traz os "
            "segundos restantes",
        }
    ),
)
async def login(dados: LoginRequest, db: AsyncSession = Depends(get_session)):
    usuario = await autenticar(db, dados.email, dados.senha)
    return TokenResponse(
        access_token=criar_token(usuario.id),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        usuario=usuario,
    )


@router.get(
    "/me",
    response_model=UsuarioResponse,
    summary="Dados de quem está logado",
    description="Conta pendente também pode consultar.",
    responses=respostas_de_erro(
        {401: "Sem token, ou token inválido, vencido ou de conta desativada"}
    ),
)
async def meus_dados(usuario: Usuario = Depends(usuario_atual)):
    return usuario
