"""Perfil da própria pessoa (BE-S5-07): dados pessoais, troca de e-mail com confirmação, troca de
senha e encerramento das sessões. A pessoa nunca altera o próprio perfil de acesso, a situação da
conta nem a capacidade de mentoria: isso é do gestor (RN24)."""

import asyncio
from datetime import timedelta

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import FinalidadeToken, PapelUsuario
from app.controllers.token_usuario import existe_token_recente, invalidar_tokens
from app.controllers.usuario import (
    criar_usuario,
    encerrar_sessoes,
    get_usuario,
    get_usuario_by_email,
)
from app.exceptions.auth import (
    email_ja_cadastrado,
    email_ja_confirmado,
    link_invalido,
    nao_autenticado,
)
from app.models import Usuario
from app.schemas.perfil import PerfilUpdate
from app.security.senha import gerar_hash
from app.services.auth import conferir_senha_atual
from app.services.confirmacao_email import enviar_confirmacao
from app.services.token_usuario import agora_utc, consumir

CAMPOS_DE_MENTOR = ("empresa_parceira", "area_atuacao")


async def _travar(db: AsyncSession, usuario: Usuario) -> Usuario:
    """Relê o usuário com a linha travada: alterações da mesma conta se enfileiram, e uma conta
    desativada ou com sessão encerrada no meio do caminho é recusada."""
    versao = usuario.versao_sessao
    await db.refresh(usuario, with_for_update=True)
    if not usuario.ativo or usuario.versao_sessao != versao:
        nao_autenticado()
    return usuario


async def atualizar_perfil(db: AsyncSession, usuario: Usuario, dados: PerfilUpdate) -> Usuario:
    valores = dados.model_dump(exclude_unset=True)
    if usuario.papel != PapelUsuario.MENTOR and any(campo in valores for campo in CAMPOS_DE_MENTOR):
        raise HTTPException(422, "Empresa e área de atuação são dados de Mentor.")
    usuario = await _travar(db, usuario)
    for campo, valor in valores.items():
        setattr(usuario, campo, valor)
    usuario.atualizado_em = agora_utc()
    db.add(usuario)
    await db.commit()
    return usuario


async def reenviar_confirmacao(db: AsyncSession, usuario: Usuario) -> None:
    """Novo link para o e-mail atual. Pedidos em sequência dentro do intervalo mínimo não geram
    outro e-mail (a resposta é a mesma), para a rota não servir de disparador de spam."""
    usuario = await _travar(db, usuario)
    if usuario.email_confirmado_em is not None:
        email_ja_confirmado()
    desde = agora_utc() - timedelta(seconds=settings.SENHA_RESET_INTERVALO_SEGUNDOS)
    if await existe_token_recente(db, usuario.id, FinalidadeToken.CONFIRMACAO_EMAIL, desde):
        return
    await enviar_confirmacao(db, usuario, usuario.email)
    await db.commit()


async def pedir_troca_de_email(
    db: AsyncSession, usuario: Usuario, novo_email: str, senha: str
) -> None:
    """O endereço só muda quando a pessoa abrir o link enviado ao NOVO endereço: assim ninguém
    passa a receber os avisos de uma conta sem provar que a caixa é sua."""
    usuario = await _travar(db, usuario)
    await conferir_senha_atual(db, usuario, senha)
    novo_email = novo_email.lower()
    if novo_email == usuario.email.lower():
        raise HTTPException(422, "O novo e-mail é igual ao atual.")
    if await get_usuario_by_email(db, novo_email) is not None:
        email_ja_cadastrado()
    await enviar_confirmacao(db, usuario, novo_email)
    await db.commit()


async def confirmar_email(db: AsyncSession, token: str) -> Usuario:
    """Abre o link do e-mail: marca o endereço como confirmado e, se o link era de uma troca,
    passa a conta para o endereço novo. Não exige login: o link costuma abrir em outro aparelho."""
    registro = await consumir(db, token, FinalidadeToken.CONFIRMACAO_EMAIL)
    usuario = await get_usuario(db, registro.usuario_id, bloquear=True)
    if usuario is None or not usuario.ativo or registro.email is None:
        await db.rollback()
        link_invalido()
    if registro.email.lower() != usuario.email.lower():
        usuario.email = registro.email.lower()
    usuario.email_confirmado_em = agora_utc()
    usuario.atualizado_em = usuario.email_confirmado_em
    db.add(usuario)
    # Um endereço novo já ocupado por outra conta sai como 409 e desfaz o uso do link
    await criar_usuario(db, usuario)
    await invalidar_tokens(db, usuario.id, FinalidadeToken.CONFIRMACAO_EMAIL, agora_utc())
    await db.commit()
    return usuario


async def trocar_senha(
    db: AsyncSession, usuario: Usuario, senha_atual: str, senha_nova: str
) -> Usuario:
    """Troca a senha e encerra as outras sessões: o token usado no pedido deixa de valer, e a
    resposta traz um novo para a pessoa seguir logada."""
    usuario = await _travar(db, usuario)
    await conferir_senha_atual(db, usuario, senha_atual)
    if senha_atual == senha_nova:
        raise HTTPException(422, "A nova senha deve ser diferente da atual.")
    usuario.senha_hash = await asyncio.to_thread(gerar_hash, senha_nova)
    usuario.versao_sessao += 1
    usuario.atualizado_em = agora_utc()
    db.add(usuario)
    # Um pedido de redefinição aberto antes da troca não pode desfazê-la depois
    await invalidar_tokens(db, usuario.id, FinalidadeToken.REDEFINICAO_SENHA, agora_utc())
    await db.commit()
    return usuario


async def encerrar_todas_as_sessoes(db: AsyncSession, usuario: Usuario) -> None:
    """RF09: encerra a sessão. Como o token não fica guardado no servidor, o encerramento vale
    para todos os tokens emitidos até agora, de todos os aparelhos."""
    await encerrar_sessoes(db, usuario.id)
    await db.commit()
