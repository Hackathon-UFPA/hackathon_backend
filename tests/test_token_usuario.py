import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, call
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FinalidadeToken
from app.models import TokenUsuario
from app.services import token_usuario

pytestmark = pytest.mark.unit

AGORA = datetime(2026, 11, 21, 12, tzinfo=UTC)
TOKEN = "token-de-teste"
HASH = hashlib.sha256(TOKEN.encode()).hexdigest()


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(token_usuario, "agora_utc", lambda: AGORA)
    return MagicMock(spec=AsyncSession)


@pytest.fixture
def registro():
    return TokenUsuario(
        usuario_id=uuid4(),
        finalidade=FinalidadeToken.REDEFINICAO_SENHA,
        token_hash=HASH,
        expira_em=AGORA + timedelta(minutes=1),
    )


@pytest.mark.parametrize(
    "finalidade,email,validade",
    [
        (FinalidadeToken.REDEFINICAO_SENHA, None, 30),
        (FinalidadeToken.CONFIRMACAO_EMAIL, "novo@example.com", 1440),
    ],
)
def test_emitir_invalida_tokens_anteriores_antes_de_salvar_o_hash(
    db, monkeypatch, finalidade, email, validade
):
    usuario_id = uuid4()
    operacoes = Mock()
    invalidar = AsyncMock()
    salvar = AsyncMock(side_effect=lambda db, registro: registro)
    operacoes.attach_mock(invalidar, "invalidar")
    operacoes.attach_mock(salvar, "salvar")
    monkeypatch.setattr(token_usuario, "invalidar_tokens", invalidar)
    monkeypatch.setattr(token_usuario, "salvar_token", salvar)
    monkeypatch.setattr(token_usuario.secrets, "token_urlsafe", lambda tamanho: TOKEN)

    token, criado = asyncio.run(
        token_usuario.emitir(db, usuario_id, finalidade, validade, email=email)
    )

    assert token == TOKEN
    assert criado.usuario_id == usuario_id
    assert criado.finalidade == finalidade
    assert criado.email == email
    assert criado.token_hash == HASH
    assert criado.expira_em == AGORA + timedelta(minutes=validade)
    assert operacoes.mock_calls == [
        call.invalidar(db, usuario_id, finalidade, AGORA),
        call.salvar(db, criado),
    ]
    db.commit.assert_not_awaited()


def test_consumir_busca_por_hash_e_finalidade_com_trava(db, monkeypatch, registro):
    buscar = AsyncMock(return_value=registro)
    monkeypatch.setattr(token_usuario, "get_token_por_hash", buscar)

    consumido = asyncio.run(token_usuario.consumir(db, TOKEN, registro.finalidade))

    assert consumido is registro
    assert registro.utilizado_em == AGORA
    buscar.assert_awaited_once_with(db, HASH, registro.finalidade, bloquear=True)
    db.refresh.assert_awaited_once_with(registro)
    db.add.assert_called_once_with(registro)
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "alteracoes",
    [
        pytest.param(None, id="inexistente"),
        pytest.param({"expira_em": AGORA}, id="expira-agora"),
        pytest.param({"expira_em": AGORA - timedelta(seconds=1)}, id="expirado"),
        pytest.param({"utilizado_em": AGORA - timedelta(seconds=1)}, id="utilizado"),
    ],
)
def test_tokens_indisponiveis_falham_sem_gravar(db, monkeypatch, registro, alteracoes):
    encontrado = None if alteracoes is None else registro.model_copy(update=alteracoes)
    buscar = AsyncMock(return_value=encontrado)
    monkeypatch.setattr(token_usuario, "get_token_por_hash", buscar)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(token_usuario.consumir(db, TOKEN, FinalidadeToken.REDEFINICAO_SENHA))

    assert erro.value.status_code == 400
    assert erro.value.detail == "Link inválido, expirado ou já utilizado."
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


def test_consumir_reavalia_o_uso_apos_atualizar_o_registro(db, monkeypatch, registro):
    monkeypatch.setattr(token_usuario, "get_token_por_hash", AsyncMock(return_value=registro))
    utilizado_em = AGORA - timedelta(seconds=1)

    def atualizar(registro):
        registro.utilizado_em = utilizado_em

    db.refresh.side_effect = atualizar

    with pytest.raises(HTTPException) as erro:
        asyncio.run(token_usuario.consumir(db, TOKEN, registro.finalidade))

    assert erro.value.status_code == 400
    assert registro.utilizado_em == utilizado_em
    db.refresh.assert_awaited_once_with(registro)
    db.add.assert_not_called()
