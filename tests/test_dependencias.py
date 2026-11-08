"""Autenticação e autorização de rotas sem iniciar servidor ou banco."""

import asyncio
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, SituacaoConta
from app.models import Usuario
from app.security import dependencias


@pytest.fixture
def usuario():
    return Usuario(email="participante@example.com", papel=PapelUsuario.PARTICIPANTE)


@pytest.fixture
def db():
    return MagicMock(spec=AsyncSession)


def test_sem_credenciais_responde_401_sem_consultar_banco(db):
    with pytest.raises(HTTPException) as erro:
        asyncio.run(dependencias.usuario_atual(None, db))

    assert erro.value.status_code == 401
    assert erro.value.headers == {"WWW-Authenticate": "Bearer"}
    db.get.assert_not_awaited()


def test_token_invalido_responde_401_sem_consultar_banco(db, monkeypatch):
    ler_token = Mock(return_value=None)
    monkeypatch.setattr(dependencias, "ler_token", ler_token)
    credenciais = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-invalido")

    with pytest.raises(HTTPException) as erro:
        asyncio.run(dependencias.usuario_atual(credenciais, db))

    assert erro.value.status_code == 401
    ler_token.assert_called_once_with("token-invalido")
    db.get.assert_not_awaited()


@pytest.mark.parametrize("estado", ["inexistente", "desativada"])
def test_token_valido_de_conta_indisponivel_responde_401(db, usuario, monkeypatch, estado):
    monkeypatch.setattr(dependencias, "ler_token", Mock(return_value=usuario.id))
    usuario.ativo = False
    db.get.return_value = None if estado == "inexistente" else usuario
    credenciais = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-valido")

    with pytest.raises(HTTPException) as erro:
        asyncio.run(dependencias.usuario_atual(credenciais, db))

    assert erro.value.status_code == 401
    db.get.assert_awaited_once_with(Usuario, usuario.id)


@pytest.mark.parametrize("situacao", list(SituacaoConta))
def test_usuario_atual_retorna_conta_do_banco_inclusive_pendente(
    db, usuario, monkeypatch, situacao
):
    usuario.situacao_conta = situacao
    monkeypatch.setattr(dependencias, "ler_token", Mock(return_value=usuario.id))
    db.get.return_value = usuario
    credenciais = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-valido")

    assert asyncio.run(dependencias.usuario_atual(credenciais, db)) is usuario
    db.get.assert_awaited_once_with(Usuario, usuario.id)


def test_usuario_ativo_rejeita_conta_pendente(usuario):
    usuario.situacao_conta = SituacaoConta.PENDENTE

    with pytest.raises(HTTPException) as erro:
        asyncio.run(dependencias.usuario_ativo(usuario))

    assert erro.value.status_code == 403
    assert "Conta pendente" in erro.value.detail


def test_usuario_ativo_aceita_conta_aprovada(usuario):
    assert asyncio.run(dependencias.usuario_ativo(usuario)) is usuario


@pytest.mark.parametrize("papel", list(PapelUsuario))
def test_exigir_papeis_permite_somente_papel_configurado_e_dev(usuario, papel):
    usuario.papel = papel
    verificar = dependencias.exigir_papeis(PapelUsuario.ORGANIZADOR)

    if papel in {PapelUsuario.ORGANIZADOR, PapelUsuario.DEV}:
        assert asyncio.run(verificar(usuario)) is usuario
    else:
        with pytest.raises(HTTPException) as erro:
            asyncio.run(verificar(usuario))
        assert erro.value.status_code == 403


@pytest.mark.parametrize("papel", [PapelUsuario.MENTOR, PapelUsuario.COMITE_TECNICO])
def test_exigir_papeis_aceita_mais_de_um_perfil(usuario, papel):
    usuario.papel = papel
    verificar = dependencias.exigir_papeis(PapelUsuario.MENTOR, PapelUsuario.COMITE_TECNICO)

    assert asyncio.run(verificar(usuario)) is usuario
