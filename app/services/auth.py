import asyncio
from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import PapelUsuario, SituacaoConta
from app.controllers.comprovante_vinculo import criar_comprovante
from app.controllers.hackathon import get_hackathon_com_inscricoes
from app.controllers.usuario import (
    criar_usuario,
    get_usuario_by_email,
    registrar_falha_de_login,
    zerar_falhas_de_login,
)
from app.exceptions.auth import conta_bloqueada, credenciais_invalidas, inscricoes_indisponiveis
from app.models import ComprovanteVinculo, Usuario
from app.schemas.auth import CadastroRequest
from app.security.senha import gastar_tempo_de_verificacao, gerar_hash, senha_confere
from app.security.token import criar_token


async def cadastrar_participante(db: AsyncSession, dados: CadastroRequest) -> Usuario:
    """Cria a conta pendente e registra o comprovante de vínculo na mesma transação (RF01, RN25).
    A conta só fica ativa quando o Comitê Científico aprovar o comprovante."""
    hackathon = await get_hackathon_com_inscricoes(db)
    if hackathon is None:
        inscricoes_indisponiveis()

    usuario = await criar_usuario(
        db,
        Usuario(
            nome=dados.nome,
            email=dados.email.lower(),
            papel=PapelUsuario.PARTICIPANTE,
            instituicao=dados.instituicao,
            curso=dados.curso,
            periodo=dados.periodo,
            senha_hash=await asyncio.to_thread(gerar_hash, dados.senha),
            situacao_conta=SituacaoConta.PENDENTE,
        ),
    )
    await criar_comprovante(
        db,
        ComprovanteVinculo(
            usuario_id=usuario.id,
            hackathon_id=hackathon.id,
            arquivo_url=str(dados.comprovante_url),
        ),
    )
    await db.commit()
    return usuario


async def autenticar(db: AsyncSession, email: str, senha: str) -> str:
    """Confere e-mail e senha e devolve o token de acesso (RF02).

    E-mail inexistente, conta sem senha, conta desativada e senha errada geram a mesma
    resposta. Depois de LOGIN_MAX_TENTATIVAS falhas seguidas a conta fica bloqueada por
    LOGIN_BLOQUEIO_MINUTOS, e nesse período nem a senha correta é aceita.
    """
    usuario = await get_usuario_by_email(db, email)
    if usuario is None or usuario.senha_hash is None or not usuario.ativo:
        await asyncio.to_thread(gastar_tempo_de_verificacao, senha)
        credenciais_invalidas()

    agora = datetime.now(UTC)
    if usuario.bloqueado_ate and usuario.bloqueado_ate > agora:
        conta_bloqueada(int((usuario.bloqueado_ate - agora).total_seconds()) + 1)

    if not await asyncio.to_thread(senha_confere, senha, usuario.senha_hash):
        await registrar_falha_de_login(
            db,
            usuario.id,
            settings.LOGIN_MAX_TENTATIVAS,
            timedelta(minutes=settings.LOGIN_BLOQUEIO_MINUTOS),
        )
        await db.commit()
        credenciais_invalidas()

    if usuario.tentativas_login or usuario.bloqueado_ate:
        zerar_falhas_de_login(db, usuario)
        await db.commit()
    return criar_token(usuario.id)
