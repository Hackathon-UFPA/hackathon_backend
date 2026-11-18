import asyncio
from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import PapelUsuario, SituacaoConta, TipoIntegrante
from app.controllers.autodeclaracao import criar_autodeclaracao
from app.controllers.comprovante_vinculo import criar_comprovante
from app.controllers.usuario import (
    criar_usuario,
    get_usuario_by_email,
    registrar_falha_de_login,
    zerar_falhas_de_login,
)
from app.exceptions.auth import (
    conta_bloqueada,
    credenciais_invalidas,
    senha_atual_incorreta,
)
from app.models import AutodeclaracaoVinculo, ComprovanteVinculo, Organizacao, Usuario
from app.schemas.auth import CadastroOrganizacaoRequest, CadastroRequest
from app.security.senha import gastar_tempo_de_verificacao, gerar_hash, senha_confere
from app.services.confirmacao_email import enviar_confirmacao
from app.services.convite import associar_convites_pendentes
from app.services.edicao_participante import resolver_edicao


async def cadastrar_participante(db: AsyncSession, dados: CadastroRequest) -> Usuario:
    """Cria a conta pendente e registra o comprovante de vínculo na mesma transação (RF01, RN25).
    A conta só fica ativa quando o Comitê Científico aprovar o comprovante.

    Estudante: instituição, curso e período ficam na conta, como antes. Profissional: organização
    e cargo não pertencem à conta, e sim à edição, então viram a autodeclaração dele na edição
    escolhida, e o comprovante inicial é do tipo PROFISSIONAL, ligado a essa declaração."""
    try:
        hackathon = await resolver_edicao(db, dados.hackathon_id)
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
        declaracao = None
        if dados.tipo == TipoIntegrante.PROFISSIONAL:
            declaracao = AutodeclaracaoVinculo(
                usuario_id=usuario.id,
                hackathon_id=hackathon.id,
                tipo=TipoIntegrante.PROFISSIONAL,
                organizacao=dados.organizacao,
                cargo=dados.cargo,
            )
            criar_autodeclaracao(db, declaracao)
            await db.flush()
        await criar_comprovante(
            db,
            ComprovanteVinculo(
                usuario_id=usuario.id,
                hackathon_id=hackathon.id,
                arquivo_url=str(dados.comprovante_url),
                tipo_vinculo=dados.tipo,
                autodeclaracao_id=declaracao.id if declaracao else None,
            ),
        )
        # BE-S5-02: associa os convites pendentes à conta, sem aceitar participação ou termos.
        await associar_convites_pendentes(db, usuario)
        # A confirmação entra na fila na mesma transação; o envio ocorre depois do commit.
        await enviar_confirmacao(db, usuario, usuario.email)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return usuario


async def cadastrar_organizacao(db: AsyncSession, dados: CadastroOrganizacaoRequest) -> Usuario:
    """Cria a organização e o primeiro Organizador dela na mesma transação. A conta já nasce
    ativa: é por ela que a organização cadastra hackathons e a própria equipe interna."""
    organizacao = Organizacao(
        nome=dados.organizacao.nome,
        tipo=dados.organizacao.tipo,
        site=str(dados.organizacao.site) if dados.organizacao.site else None,
        descricao=dados.organizacao.descricao,
    )
    db.add(organizacao)
    await db.flush()
    usuario = await criar_usuario(
        db,
        Usuario(
            nome=dados.responsavel.nome,
            email=dados.responsavel.email.lower(),
            papel=PapelUsuario.ORGANIZADOR,
            organizacao_id=organizacao.id,
            senha_hash=await asyncio.to_thread(gerar_hash, dados.responsavel.senha),
            situacao_conta=SituacaoConta.ATIVA,
        ),
    )
    await db.commit()
    await db.refresh(usuario)
    return usuario


async def autenticar(db: AsyncSession, email: str, senha: str) -> Usuario:
    """Confere e-mail e senha e devolve o usuário autenticado (RF02).

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
    return usuario


async def conferir_senha_atual(db: AsyncSession, usuario: Usuario, senha: str) -> None:
    """Exige a senha de quem já está logado antes de uma troca sensível (e-mail ou senha).

    Um token roubado não basta para trocar a senha: e, como no login, as tentativas erradas contam
    para o bloqueio da conta, então a rota não serve para adivinhar a senha. Sem commit no
    acerto; no erro, a falha é gravada e confirmada antes da resposta."""
    agora = datetime.now(UTC)
    if usuario.bloqueado_ate and usuario.bloqueado_ate > agora:
        conta_bloqueada(int((usuario.bloqueado_ate - agora).total_seconds()) + 1)
    if usuario.senha_hash is None or not await asyncio.to_thread(
        senha_confere, senha, usuario.senha_hash
    ):
        await registrar_falha_de_login(
            db,
            usuario.id,
            settings.LOGIN_MAX_TENTATIVAS,
            timedelta(minutes=settings.LOGIN_BLOQUEIO_MINUTOS),
        )
        await db.commit()
        senha_atual_incorreta()
    if usuario.tentativas_login or usuario.bloqueado_ate:
        zerar_falhas_de_login(db, usuario)
