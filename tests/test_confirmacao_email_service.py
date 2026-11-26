import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FinalidadeToken, PapelUsuario, TipoEmail
from app.models import Usuario
from app.services import confirmacao_email

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "nome,destinatario,saudacao",
    [
        ("Ana", "atual@example.com", "Ana"),
        (None, "novo@example.com", "participante"),
    ],
)
def test_confirmacao_envia_para_o_endereco_a_confirmar(monkeypatch, nome, destinatario, saudacao):
    db = MagicMock(spec=AsyncSession)
    usuario = Usuario(nome=nome, email="atual@example.com", papel=PapelUsuario.PARTICIPANTE)
    registro = SimpleNamespace(id=uuid4())
    emitir = AsyncMock(return_value=("token-de-confirmacao", registro))
    enfileirar = AsyncMock()
    monkeypatch.setattr(confirmacao_email, "emitir", emitir)
    monkeypatch.setattr(confirmacao_email, "enfileirar", enfileirar)
    monkeypatch.setattr(confirmacao_email.settings, "FRONTEND_URL", "https://app.example.com/")
    monkeypatch.setattr(confirmacao_email.settings, "EMAIL_CONFIRMACAO_MINUTOS", 90)

    asyncio.run(confirmacao_email.enviar_confirmacao(db, usuario, destinatario))

    emitir.assert_awaited_once_with(
        db, usuario.id, FinalidadeToken.CONFIRMACAO_EMAIL, 90, email=destinatario
    )
    enfileirar.assert_awaited_once_with(
        db,
        TipoEmail.CONFIRMACAO_EMAIL,
        destinatario_email=destinatario,
        destinatario_nome=nome,
        usuario_id=usuario.id,
        contexto={
            "nome": saudacao,
            "link": "https://app.example.com/confirmar-email#token=token-de-confirmacao",
        },
        chave=f"confirmacao-email:{registro.id}",
    )
    assert usuario.email == "atual@example.com"
    db.commit.assert_not_awaited()


def test_falha_ao_emitir_confirmacao_nao_enfileira_email(monkeypatch):
    db = MagicMock(spec=AsyncSession)
    usuario = Usuario(email="atual@example.com", papel=PapelUsuario.PARTICIPANTE)
    falha = RuntimeError("Falha ao gravar o token")
    enfileirar = AsyncMock()
    monkeypatch.setattr(confirmacao_email, "emitir", AsyncMock(side_effect=falha))
    monkeypatch.setattr(confirmacao_email, "enfileirar", enfileirar)

    with pytest.raises(RuntimeError) as erro:
        asyncio.run(confirmacao_email.enviar_confirmacao(db, usuario, usuario.email))

    assert erro.value is falha
    enfileirar.assert_not_awaited()
    db.commit.assert_not_awaited()
