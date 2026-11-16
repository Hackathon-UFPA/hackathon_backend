"""Recuperação de senha por link de uso único enviado por e-mail (RF04, BE-S5-07)."""

import asyncio
from datetime import timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import FinalidadeToken, TipoEmail
from app.controllers.token_usuario import existe_token_recente, invalidar_tokens
from app.controllers.usuario import get_usuario, get_usuario_by_email
from app.exceptions.auth import link_invalido
from app.security.senha import gerar_hash
from app.services.email import enfileirar, link_front
from app.services.token_usuario import agora_utc, consumir, emitir


async def solicitar(db: AsyncSession, email: str) -> None:
    """Envia o link de redefinição se a conta existir e puder entrar. Não devolve nada que
    diferencie os casos: quem chama responde sempre o mesmo, e a rota não serve para descobrir
    quais e-mails têm conta (RNF14 a RNF17).

    Ficam sem e-mail: endereço sem conta, conta desativada e conta sem senha (mentor que ainda
    não concluiu o convite: o caminho dele é o convite). Pedidos em sequência dentro do
    intervalo mínimo também não geram outro e-mail.
    """
    encontrado = await get_usuario_by_email(db, email)
    if encontrado is None:
        return
    # Trava a conta: dois pedidos simultâneos se enfileiram e o segundo vê o intervalo
    usuario = await get_usuario(db, encontrado.id, bloquear=True)
    if usuario is None or not usuario.ativo or usuario.senha_hash is None:
        await db.rollback()
        return
    desde = agora_utc() - timedelta(seconds=settings.SENHA_RESET_INTERVALO_SEGUNDOS)
    if await existe_token_recente(db, usuario.id, FinalidadeToken.REDEFINICAO_SENHA, desde):
        await db.rollback()
        return
    token, registro = await emitir(
        db, usuario.id, FinalidadeToken.REDEFINICAO_SENHA, settings.SENHA_RESET_MINUTOS
    )
    await enfileirar(
        db,
        TipoEmail.RECUPERACAO_SENHA,
        destinatario_email=usuario.email,
        destinatario_nome=usuario.nome,
        usuario_id=usuario.id,
        contexto={
            "nome": usuario.nome or "participante",
            "link": link_front(f"/redefinir-senha#token={token}"),
            "validade_minutos": settings.SENHA_RESET_MINUTOS,
        },
        chave=f"recuperacao-senha:{registro.id}",
    )
    await db.commit()


async def redefinir(db: AsyncSession, token: str, senha_nova: str) -> None:
    """Usa o link: grava a nova senha, encerra todas as sessões abertas e libera o login caso a
    conta estivesse bloqueada por tentativas erradas. Quem chega aqui provou a posse do e-mail,
    então o endereço também passa a confirmado."""
    registro = await consumir(db, token, FinalidadeToken.REDEFINICAO_SENHA)
    usuario = await get_usuario(db, registro.usuario_id, bloquear=True)
    if usuario is None or not usuario.ativo:
        # Desfaz o uso do link: ele não serve para uma conta desativada
        await db.rollback()
        link_invalido()
    agora = agora_utc()
    usuario.senha_hash = await asyncio.to_thread(gerar_hash, senha_nova)
    usuario.versao_sessao += 1
    usuario.tentativas_login = 0
    usuario.bloqueado_ate = None
    usuario.email_confirmado_em = usuario.email_confirmado_em or agora
    usuario.atualizado_em = agora
    db.add(usuario)
    await invalidar_tokens(db, usuario.id, FinalidadeToken.REDEFINICAO_SENHA, agora)
    await db.commit()
