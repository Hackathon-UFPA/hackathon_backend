"""Autenticação e autorização de rotas sem iniciar servidor ou banco."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, SituacaoConta
from app.models import Usuario
from app.security import dependencias

pytestmark = pytest.mark.unit


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
    ler_sessao = Mock(return_value=None)
    monkeypatch.setattr(dependencias, "ler_sessao", ler_sessao)
    credenciais = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-invalido")

    with pytest.raises(HTTPException) as erro:
        asyncio.run(dependencias.usuario_atual(credenciais, db))

    assert erro.value.status_code == 401
    ler_sessao.assert_called_once_with("token-invalido")
    db.get.assert_not_awaited()


@pytest.mark.parametrize("estado", ["inexistente", "desativada", "sessao-revogada"])
def test_token_valido_de_conta_indisponivel_responde_401(db, usuario, monkeypatch, estado):
    monkeypatch.setattr(
        dependencias, "ler_sessao", Mock(return_value=(usuario.id, usuario.versao_sessao))
    )
    usuario.ativo = estado != "desativada"
    if estado == "sessao-revogada":
        usuario.versao_sessao += 1
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
    monkeypatch.setattr(
        dependencias, "ler_sessao", Mock(return_value=(usuario.id, usuario.versao_sessao))
    )
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


def test_visitante_pode_consultar_rota_publica_sem_consultar_banco(db):
    assert asyncio.run(dependencias.usuario_opcional(None, db)) is None
    db.get.assert_not_awaited()


def test_token_invalido_na_rota_publica_ainda_retorna_401(db, monkeypatch):
    monkeypatch.setattr(dependencias, "ler_sessao", Mock(return_value=None))
    credenciais = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-invalido")

    with pytest.raises(HTTPException) as erro:
        asyncio.run(dependencias.usuario_opcional(credenciais, db))

    assert erro.value.status_code == 401
    db.get.assert_not_awaited()


@pytest.mark.parametrize(
    "dependencia", [dependencias.usuario_ativo, dependencias.usuario_convidado]
)
@pytest.mark.parametrize("estado", ["sem-aceite", "sem-perfil", "completo"])
def test_mentor_precisa_concluir_ativacao_nas_duas_dependencias(usuario, dependencia, estado):
    agora = datetime(2026, 11, 7, tzinfo=UTC)
    usuario.papel = PapelUsuario.MENTOR
    usuario.mentor_ativado_em = None if estado == "sem-aceite" else agora
    usuario.mentor_perfil_concluido_em = None if estado == "sem-perfil" else agora

    if estado == "completo":
        assert asyncio.run(dependencia(usuario)) is usuario
    else:
        with pytest.raises(HTTPException) as erro:
            asyncio.run(dependencia(usuario))
        assert erro.value.status_code == 403
        assert "RN33" in erro.value.detail


def test_participante_pendente_pode_responder_convite(usuario):
    usuario.situacao_conta = SituacaoConta.PENDENTE
    assert asyncio.run(dependencias.usuario_convidado(usuario)) is usuario


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
