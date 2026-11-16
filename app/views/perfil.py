from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.db.db import get_session
from app.models import Usuario
from app.schemas.auth import TokenResponse
from app.schemas.perfil import (
    MensagemResponse,
    PerfilUpdate,
    TrocaEmailRequest,
    TrocaSenhaRequest,
)
from app.schemas.usuario import UsuarioResponse
from app.security.dependencias import usuario_atual
from app.security.token import criar_token
from app.services import perfil as servico
from app.utils.openapi import respostas_de_erro

router = APIRouter(prefix="/me", tags=["Perfil"])

ERRO_401 = "Sem token, ou token inválido, vencido, encerrado ou de conta desativada"
ERRO_SENHA = (
    "Senha atual incorreta (403). Cada erro conta para o bloqueio da conta, como no login (429)"
)


@router.get(
    "",
    response_model=UsuarioResponse,
    summary="Meus dados",
    description="RF05. Conta pendente também pode consultar. Igual a `GET /auth/me`.",
    responses=respostas_de_erro({401: ERRO_401}),
)
async def meus_dados(usuario: Usuario = Depends(usuario_atual)):
    return usuario


@router.patch(
    "",
    response_model=UsuarioResponse,
    summary="Atualizar meus dados",
    description=(
        "RF05. Altera só o que foi enviado: nome, instituição, curso e período; Mentor também "
        "empresa e área de atuação. **Perfil, situação da conta, e-mail e capacidade de mentoria "
        "não podem ser alterados aqui**: enviar `papel`, `ativo`, `situacao_conta`, `email` ou "
        "qualquer campo fora da lista dá 422. O e-mail muda por `POST /me/email`, com "
        "confirmação."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            422: "Campo desconhecido, nulo ou inválido, ou dado de Mentor enviado por outro perfil",
        }
    ),
)
async def atualizar_meus_dados(
    dados: PerfilUpdate,
    usuario: Usuario = Depends(usuario_atual),
    db: AsyncSession = Depends(get_session),
):
    return await servico.atualizar_perfil(db, usuario, dados)


@router.post(
    "/senha",
    response_model=TokenResponse,
    summary="Trocar a senha",
    description=(
        "RF05, RNF15. Exige a senha atual. Depois da troca, **todas as sessões anteriores "
        "deixam de valer**, inclusive o token usado neste pedido: a resposta traz um token novo "
        "para a pessoa seguir logada. Links de redefinição ainda abertos são gastos."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_SENHA,
            422: "Senha nova fraca ou igual à atual",
            429: "Conta bloqueada por tentativas erradas",
        }
    ),
)
async def trocar_senha(
    dados: TrocaSenhaRequest,
    usuario: Usuario = Depends(usuario_atual),
    db: AsyncSession = Depends(get_session),
):
    usuario = await servico.trocar_senha(db, usuario, dados.senha_atual, dados.senha_nova)
    return TokenResponse(
        access_token=criar_token(usuario.id, usuario.versao_sessao),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        usuario=usuario,
    )


@router.post(
    "/email",
    response_model=MensagemResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pedir a troca do e-mail",
    description=(
        "RF01, RF05. Exige a senha atual. O endereço **não muda agora**: um link de uso único é "
        "enviado ao novo e-mail, e a conta só passa a usá-lo quando o link for aberto "
        "(`POST /auth/confirmar-email`). Um novo pedido gasta o link anterior."
    ),
    responses=respostas_de_erro(
        {
            401: ERRO_401,
            403: ERRO_SENHA,
            409: "O novo e-mail já pertence a outra conta",
            422: "E-mail inválido ou igual ao atual",
            429: "Conta bloqueada por tentativas erradas",
        }
    ),
)
async def pedir_troca_de_email(
    dados: TrocaEmailRequest,
    usuario: Usuario = Depends(usuario_atual),
    db: AsyncSession = Depends(get_session),
):
    await servico.pedir_troca_de_email(db, usuario, dados.novo_email, dados.senha)
    return MensagemResponse(detail="Enviamos um link de confirmação para o novo e-mail.")


@router.post(
    "/confirmacao-email",
    response_model=MensagemResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reenviar o link de confirmação do e-mail",
    description=(
        "RF01. Envia um novo link para o e-mail atual e gasta o anterior. Pedidos dentro de "
        "`SENHA_RESET_INTERVALO_SEGUNDOS` não geram outro e-mail, mas têm a mesma resposta."
    ),
    responses=respostas_de_erro({401: ERRO_401, 409: "O e-mail desta conta já está confirmado"}),
)
async def reenviar_confirmacao(
    usuario: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_session)
):
    await servico.reenviar_confirmacao(db, usuario)
    return MensagemResponse(detail="Enviamos um link de confirmação para o seu e-mail.")
