import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FinalidadeToken, PapelUsuario, TipoEmail
from app.models import Usuario
from app.services import recuperacao_senha

pytestmark = pytest.mark.unit

AGORA = datetime(2026, 11, 7, 12, tzinfo=UTC)
FINALIDADE = FinalidadeToken.REDEFINICAO_SENHA


@pytest.fixture
def cenario(monkeypatch):
    usuario = Usuario(
        email="ana@example.com", nome="Ana", papel=PapelUsuario.PARTICIPANTE, senha_hash="antigo"
    )
    registro = SimpleNamespace(id=uuid4(), usuario_id=usuario.id)
    colaboradores = {
        "agora_utc": Mock(return_value=AGORA),
        "get_usuario_by_email": AsyncMock(return_value=usuario),
        "get_usuario": AsyncMock(return_value=usuario),
        "existe_token_recente": AsyncMock(return_value=False),
        "emitir": AsyncMock(return_value=("token-unico", registro)),
        "consumir": AsyncMock(return_value=registro),
        "enfileirar": AsyncMock(),
        "invalidar_tokens": AsyncMock(),
        "gerar_hash": Mock(return_value="novo-hash"),
    }
    for atributo, mock in colaboradores.items():
        monkeypatch.setattr(recuperacao_senha, atributo, mock)
    for nome, valor in {
        "SENHA_RESET_INTERVALO_SEGUNDOS": 30,
        "SENHA_RESET_MINUTOS": 45,
        "FRONTEND_URL": "https://app.example.com/",
    }.items():
        monkeypatch.setattr(recuperacao_senha.settings, nome, valor)
    return SimpleNamespace(
        db=MagicMock(spec=AsyncSession), usuario=usuario, registro=registro, **colaboradores
    )


@pytest.mark.parametrize(
    "estado", ["sem-conta", "removida", "desativada", "sem-senha", "solicitacao-recente"]
)
def test_solicitacao_inelegivel_nao_emite_token_ou_email(cenario, estado):
    if estado == "sem-conta":
        cenario.get_usuario_by_email.return_value = None
    elif estado == "removida":
        cenario.get_usuario.return_value = None
    elif estado == "desativada":
        cenario.usuario.ativo = False
    elif estado == "sem-senha":
        cenario.usuario.senha_hash = None
    else:
        cenario.existe_token_recente.return_value = True

    assert asyncio.run(recuperacao_senha.solicitar(cenario.db, cenario.usuario.email)) is None

    cenario.emitir.assert_not_awaited()
    cenario.enfileirar.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()
    if estado == "sem-conta":
        cenario.get_usuario.assert_not_awaited()
        cenario.db.rollback.assert_not_awaited()
    else:
        cenario.get_usuario.assert_awaited_once_with(cenario.db, cenario.usuario.id, bloquear=True)
        cenario.db.rollback.assert_awaited_once_with()


@pytest.mark.parametrize(("nome", "saudacao"), [("Ana", "Ana"), (None, "participante")])
def test_solicitacao_valida_emite_e_enfileira_o_link_na_mesma_transacao(cenario, nome, saudacao):
    usuario = cenario.usuario
    usuario.nome = nome

    asyncio.run(recuperacao_senha.solicitar(cenario.db, usuario.email))

    cenario.existe_token_recente.assert_awaited_once_with(
        cenario.db, usuario.id, FINALIDADE, AGORA - timedelta(seconds=30)
    )
    cenario.emitir.assert_awaited_once_with(cenario.db, usuario.id, FINALIDADE, 45)
    cenario.enfileirar.assert_awaited_once_with(
        cenario.db,
        TipoEmail.RECUPERACAO_SENHA,
        destinatario_email=usuario.email,
        destinatario_nome=nome,
        usuario_id=usuario.id,
        contexto={
            "nome": saudacao,
            "link": "https://app.example.com/redefinir-senha#token=token-unico",
            "validade_minutos": 45,
        },
        chave=f"recuperacao-senha:{cenario.registro.id}",
    )
    cenario.db.commit.assert_awaited_once_with()


@pytest.mark.parametrize("estado", ["removida", "desativada"])
def test_redefinicao_desfaz_consumo_quando_a_conta_nao_pode_ser_alterada(cenario, estado):
    if estado == "removida":
        cenario.get_usuario.return_value = None
    else:
        cenario.usuario.ativo = False

    with pytest.raises(HTTPException) as erro:
        asyncio.run(recuperacao_senha.redefinir(cenario.db, "token-unico", "novaSenha123"))

    assert erro.value.status_code == 400
    cenario.consumir.assert_awaited_once_with(cenario.db, "token-unico", FINALIDADE)
    cenario.db.rollback.assert_awaited_once_with()
    cenario.gerar_hash.assert_not_called()
    cenario.invalidar_tokens.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("confirmado", [False, True])
def test_redefinicao_revoga_sessoes_e_links_e_desbloqueia_a_conta(cenario, confirmado):
    usuario = cenario.usuario
    usuario.versao_sessao = 4
    usuario.tentativas_login = 5
    usuario.bloqueado_ate = AGORA + timedelta(minutes=15)
    confirmacao_anterior = AGORA - timedelta(days=1) if confirmado else None
    usuario.email_confirmado_em = confirmacao_anterior

    asyncio.run(recuperacao_senha.redefinir(cenario.db, "token-unico", "novaSenha123"))

    cenario.get_usuario.assert_awaited_once_with(cenario.db, usuario.id, bloquear=True)
    cenario.gerar_hash.assert_called_once_with("novaSenha123")
    assert usuario.senha_hash == "novo-hash"
    assert usuario.versao_sessao == 5
    assert usuario.tentativas_login == 0
    assert usuario.bloqueado_ate is None
    assert usuario.email_confirmado_em == (confirmacao_anterior or AGORA)
    assert usuario.atualizado_em == AGORA
    cenario.db.add.assert_called_once_with(usuario)
    cenario.invalidar_tokens.assert_awaited_once_with(cenario.db, usuario.id, FINALIDADE, AGORA)
    cenario.db.commit.assert_awaited_once_with()
