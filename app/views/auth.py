from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.db.db import get_session
from app.models import Usuario
from app.schemas.auth import (
    CadastroOrganizacaoRequest,
    CadastroRequest,
    LoginRequest,
    TokenResponse,
)
from app.schemas.perfil import (
    ConfirmarEmailRequest,
    MensagemResponse,
    RecuperarSenhaRequest,
    RedefinirSenhaRequest,
    SessaoResponse,
)
from app.schemas.usuario import UsuarioResponse
from app.security.dependencias import bearer, usuario_atual
from app.security.token import criar_token, segundos_restantes
from app.services import perfil as servico_perfil
from app.services import recuperacao_senha
from app.services.auth import autenticar, cadastrar_organizacao, cadastrar_participante
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
        "A conta só fica ativa quando o Comitê Científico aprovar o comprovante. Um e-mail de "
        "confirmação do endereço é enviado (informativo: não bloqueia o acesso)."
    ),
    responses=respostas_de_erro(
        {409: "E-mail já cadastrado, ou nenhum hackathon com inscrições abertas no momento"}
    ),
)
async def cadastrar(dados: CadastroRequest, db: AsyncSession = Depends(get_session)):
    return await cadastrar_participante(db, dados)


@router.post(
    "/cadastro-organizacao",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar organização",
    description=(
        "Cadastro público, sem login, de uma empresa ou instituição de ensino que quer "
        "organizar hackathons na plataforma. Cria a organização e o primeiro **Organizador** "
        "dela, com a conta ativa, e já devolve o token de acesso, como o login."
    ),
    responses=respostas_de_erro({409: "E-mail do responsável já cadastrado"}),
)
async def cadastrar_nova_organizacao(
    dados: CadastroOrganizacaoRequest, db: AsyncSession = Depends(get_session)
):
    usuario = await cadastrar_organizacao(db, dados)
    return TokenResponse(
        access_token=criar_token(usuario.id),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        usuario=usuario,
    )


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
        access_token=criar_token(usuario.id, usuario.versao_sessao),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        usuario=usuario,
    )


@router.get(
    "/me",
    response_model=UsuarioResponse,
    summary="Dados de quem está logado",
    description="Conta pendente também pode consultar. Igual a `GET /me`.",
    responses=respostas_de_erro(
        {401: "Sem token, ou token inválido, vencido, encerrado ou de conta desativada"}
    ),
)
async def meus_dados(usuario: Usuario = Depends(usuario_atual)):
    return usuario


@router.post(
    "/recuperar-senha",
    response_model=MensagemResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pedir o link para redefinir a senha",
    description=(
        "Rota pública (RF04). A resposta é **sempre a mesma**, exista ou não conta com o e-mail, "
        "para não revelar quem está cadastrado. Se a conta existir e estiver ativa, o link de uso "
        "único é enviado por e-mail e vale `SENHA_RESET_MINUTOS`. Um novo pedido gasta o link "
        "anterior; pedidos em sequência dentro de `SENHA_RESET_INTERVALO_SEGUNDOS` não geram "
        "outro e-mail."
    ),
    responses=respostas_de_erro({422: "E-mail em formato inválido"}),
)
async def recuperar_senha(dados: RecuperarSenhaRequest, db: AsyncSession = Depends(get_session)):
    await recuperacao_senha.solicitar(db, dados.email)
    return MensagemResponse(
        detail="Se existir uma conta ativa com este e-mail, enviamos o link para redefinir a senha."
    )


@router.post(
    "/redefinir-senha",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Definir a nova senha com o link do e-mail",
    description=(
        "Rota pública (RF04). Grava a nova senha, **encerra todas as sessões abertas** e libera o "
        "login se a conta estava bloqueada por tentativas erradas. O link funciona uma única vez; "
        "a senha segue a mesma regra do cadastro."
    ),
    responses=respostas_de_erro(
        {
            400: "Link inválido, vencido ou já utilizado (a mensagem é a mesma nos três casos)",
            422: "Senha fraca ou token em formato inválido",
        }
    ),
)
async def redefinir_senha(dados: RedefinirSenhaRequest, db: AsyncSession = Depends(get_session)):
    await recuperacao_senha.redefinir(db, dados.token, dados.senha_nova)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/confirmar-email",
    response_model=UsuarioResponse,
    summary="Confirmar o e-mail com o link recebido",
    description=(
        "Rota pública (RF01): o link costuma abrir em outro aparelho, então não exige login. "
        "Marca o e-mail como confirmado e, se o link veio de um pedido de troca de e-mail "
        "(`POST /me/email`), passa a conta para o novo endereço. A confirmação é informativa: "
        "não bloqueia o acesso."
    ),
    responses=respostas_de_erro(
        {
            400: "Link inválido, vencido ou já utilizado",
            409: "O novo endereço foi cadastrado por outra conta antes da confirmação",
            422: "Token em formato inválido",
        }
    ),
)
async def confirmar_email(dados: ConfirmarEmailRequest, db: AsyncSession = Depends(get_session)):
    return await servico_perfil.confirmar_email(db, dados.token)


@router.get(
    "/sessao",
    response_model=SessaoResponse,
    summary="Quando a sessão atual vence",
    description=(
        "RF09: a interface usa para avisar a pessoa antes de a sessão expirar. O token não é "
        "renovado: depois do vencimento é preciso entrar de novo."
    ),
    responses=respostas_de_erro(
        {401: "Sem token, ou token inválido, vencido, encerrado ou de conta desativada"}
    ),
)
async def sessao(
    credenciais: HTTPAuthorizationCredentials = Depends(bearer),
    _: Usuario = Depends(usuario_atual),
):
    restante = segundos_restantes(credenciais.credentials) or 0
    return SessaoResponse(
        expira_em=datetime.now(UTC) + timedelta(seconds=restante), segundos_restantes=restante
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Encerrar a sessão",
    description=(
        "RF09. Como o token não fica guardado no servidor, o encerramento invalida **todos** os "
        "tokens emitidos até agora para a conta, em todos os aparelhos. Conta pendente também "
        "pode encerrar."
    ),
    responses=respostas_de_erro({401: "Sem token, ou token inválido, vencido ou já encerrado"}),
)
async def logout(
    usuario: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_session)
):
    await servico_perfil.encerrar_todas_as_sessoes(db, usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
