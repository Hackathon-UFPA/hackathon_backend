import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FinalidadeToken, PapelUsuario
from app.models import Usuario
from app.schemas.perfil import PerfilUpdate
from app.services import perfil

pytestmark = pytest.mark.unit

AGORA = datetime(2026, 11, 7, 12, tzinfo=UTC)


@pytest.fixture
def cenario(monkeypatch):
    usuario = Usuario(
        email="ana@example.com",
        nome="Ana",
        papel=PapelUsuario.PARTICIPANTE,
        curso="Engenharia",
        senha_hash="hash-atual",
    )
    registro = SimpleNamespace(usuario_id=usuario.id, email=usuario.email)
    colaboradores = {
        "agora_utc": Mock(return_value=AGORA),
        "conferir_senha_atual": AsyncMock(),
        "enviar_confirmacao": AsyncMock(),
        "existe_token_recente": AsyncMock(return_value=False),
        "get_usuario_by_email": AsyncMock(return_value=None),
        "consumir": AsyncMock(return_value=registro),
        "get_usuario": AsyncMock(return_value=usuario),
        "criar_usuario": AsyncMock(),
        "invalidar_tokens": AsyncMock(),
        "encerrar_sessoes": AsyncMock(),
        "gerar_hash": Mock(return_value="hash-novo"),
    }
    for atributo, mock in colaboradores.items():
        monkeypatch.setattr(perfil, atributo, mock)
    monkeypatch.setattr(perfil.settings, "SENHA_RESET_INTERVALO_SEGUNDOS", 30)
    return SimpleNamespace(
        db=MagicMock(spec=AsyncSession), usuario=usuario, registro=registro, **colaboradores
    )


@pytest.mark.parametrize("campo", ["papel", "situacao_conta", "ativo", "email", "max_equipes"])
def test_dados_reservados_nao_fazem_parte_do_contrato_de_edicao(campo):
    with pytest.raises(ValidationError) as erro:
        PerfilUpdate.model_validate({campo: "qualquer"})

    assert erro.value.errors()[0]["type"] == "extra_forbidden"


def test_edicao_rejeita_nulo_mas_aceita_ausencia():
    with pytest.raises(ValidationError, match="não podem ser nulos"):
        PerfilUpdate(nome=None)

    assert PerfilUpdate().model_dump(exclude_unset=True) == {}


def test_edicao_altera_somente_os_campos_enviados(cenario):
    usuario = cenario.usuario
    resultado = asyncio.run(
        perfil.atualizar_perfil(cenario.db, usuario, PerfilUpdate(nome=" Ana Costa "))
    )

    assert resultado is usuario
    assert usuario.nome == "Ana Costa"
    assert usuario.curso == "Engenharia"
    assert usuario.email == "ana@example.com"
    assert usuario.atualizado_em == AGORA
    cenario.db.refresh.assert_awaited_once_with(usuario, with_for_update=True)
    cenario.db.add.assert_called_once_with(usuario)
    cenario.db.commit.assert_awaited_once_with()


@pytest.mark.parametrize("mentor", [False, True])
def test_campos_de_mentoria_exigem_o_papel_de_mentor(cenario, mentor):
    usuario = cenario.usuario
    dados = PerfilUpdate(empresa_parceira="UFPA", area_atuacao="Engenharia")
    if mentor:
        usuario.papel = PapelUsuario.MENTOR
        asyncio.run(perfil.atualizar_perfil(cenario.db, usuario, dados))
        assert (usuario.empresa_parceira, usuario.area_atuacao) == ("UFPA", "Engenharia")
        cenario.db.commit.assert_awaited_once_with()
    else:
        with pytest.raises(HTTPException) as erro:
            asyncio.run(perfil.atualizar_perfil(cenario.db, usuario, dados))
        assert erro.value.status_code == 422
        cenario.db.refresh.assert_not_awaited()
        cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("mudanca", [{"ativo": False}, {"versao_sessao": 1}])
def test_conta_e_sessao_sao_revalidadas_apos_a_trava(cenario, mudanca):
    def mudar_conta(usuario, *, with_for_update):
        assert with_for_update is True
        for campo, valor in mudanca.items():
            setattr(usuario, campo, valor)

    cenario.db.refresh.side_effect = mudar_conta

    with pytest.raises(HTTPException) as erro:
        asyncio.run(
            perfil.atualizar_perfil(cenario.db, cenario.usuario, PerfilUpdate(nome="Outro"))
        )

    assert erro.value.status_code == 401
    assert cenario.usuario.nome == "Ana"
    cenario.db.add.assert_not_called()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("estado", ["confirmado", "token-recente", "sem-token"])
def test_reenvio_de_confirmacao_respeita_situacao_e_intervalo(cenario, estado):
    usuario = cenario.usuario
    if estado == "confirmado":
        usuario.email_confirmado_em = AGORA
        with pytest.raises(HTTPException) as erro:
            asyncio.run(perfil.reenviar_confirmacao(cenario.db, usuario))
        assert erro.value.status_code == 409
        cenario.existe_token_recente.assert_not_awaited()
    else:
        cenario.existe_token_recente.return_value = estado == "token-recente"
        asyncio.run(perfil.reenviar_confirmacao(cenario.db, usuario))
        cenario.existe_token_recente.assert_awaited_once_with(
            cenario.db, usuario.id, FinalidadeToken.CONFIRMACAO_EMAIL, AGORA - timedelta(seconds=30)
        )

    if estado == "sem-token":
        cenario.enviar_confirmacao.assert_awaited_once_with(cenario.db, usuario, usuario.email)
        cenario.db.commit.assert_awaited_once_with()
    else:
        cenario.enviar_confirmacao.assert_not_awaited()
        cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize(("estado", "status"), [("mesmo", 422), ("ocupado", 409), ("novo", None)])
def test_troca_de_email_so_enfileira_confirmacao_para_endereco_novo(cenario, estado, status):
    usuario = cenario.usuario
    if estado == "ocupado":
        cenario.get_usuario_by_email.return_value = Usuario(email="novo@example.com")
    destino = "ANA@example.com" if estado == "mesmo" else "NOVO@example.com"
    operacao = perfil.pedir_troca_de_email(cenario.db, usuario, destino, "senha-atual")

    if status is None:
        asyncio.run(operacao)
        cenario.enviar_confirmacao.assert_awaited_once_with(cenario.db, usuario, "novo@example.com")
        cenario.db.commit.assert_awaited_once_with()
    else:
        with pytest.raises(HTTPException) as erro:
            asyncio.run(operacao)
        assert erro.value.status_code == status
        cenario.enviar_confirmacao.assert_not_awaited()
        cenario.db.commit.assert_not_awaited()

    assert usuario.email == "ana@example.com"
    cenario.conferir_senha_atual.assert_awaited_once_with(cenario.db, usuario, "senha-atual")
    if estado == "mesmo":
        cenario.get_usuario_by_email.assert_not_awaited()


@pytest.mark.parametrize("estado", ["sem-conta", "desativada", "sem-endereco"])
def test_confirmacao_desfaz_uso_do_link_quando_nao_pode_atualizar(cenario, estado):
    if estado == "sem-conta":
        cenario.get_usuario.return_value = None
    elif estado == "desativada":
        cenario.usuario.ativo = False
    else:
        cenario.registro.email = None

    with pytest.raises(HTTPException) as erro:
        asyncio.run(perfil.confirmar_email(cenario.db, "token-unico"))

    assert erro.value.status_code == 400
    cenario.db.rollback.assert_awaited_once_with()
    cenario.criar_usuario.assert_not_awaited()
    cenario.invalidar_tokens.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("email", ["ANA@example.com", "NOVO@example.com"])
def test_confirmacao_grava_endereco_normalizado_e_revoga_links_anteriores(cenario, email):
    usuario = cenario.usuario
    cenario.registro.email = email

    assert asyncio.run(perfil.confirmar_email(cenario.db, "token-unico")) is usuario

    cenario.consumir.assert_awaited_once_with(
        cenario.db, "token-unico", FinalidadeToken.CONFIRMACAO_EMAIL
    )
    cenario.get_usuario.assert_awaited_once_with(cenario.db, usuario.id, bloquear=True)
    assert usuario.email == email.lower()
    assert usuario.email_confirmado_em == usuario.atualizado_em == AGORA
    cenario.invalidar_tokens.assert_awaited_once_with(
        cenario.db, usuario.id, FinalidadeToken.CONFIRMACAO_EMAIL, AGORA
    )
    cenario.db.commit.assert_awaited_once_with()


def test_troca_de_senha_rejeita_senha_igual(cenario):
    with pytest.raises(HTTPException) as erro:
        asyncio.run(perfil.trocar_senha(cenario.db, cenario.usuario, "atual123", "atual123"))

    assert erro.value.status_code == 422
    cenario.gerar_hash.assert_not_called()
    cenario.invalidar_tokens.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


def test_troca_de_senha_revoga_sessoes_e_links_de_redefinicao(cenario):
    usuario = cenario.usuario
    usuario.versao_sessao = 3

    assert asyncio.run(perfil.trocar_senha(cenario.db, usuario, "atual123", "nova1234")) is usuario

    cenario.conferir_senha_atual.assert_awaited_once_with(cenario.db, usuario, "atual123")
    assert (usuario.senha_hash, usuario.versao_sessao, usuario.atualizado_em) == (
        "hash-novo",
        4,
        AGORA,
    )
    cenario.invalidar_tokens.assert_awaited_once_with(
        cenario.db, usuario.id, FinalidadeToken.REDEFINICAO_SENHA, AGORA
    )
    cenario.db.commit.assert_awaited_once_with()


def test_logout_em_todos_os_dispositivos_confirma_revogacao(cenario):
    asyncio.run(perfil.encerrar_todas_as_sessoes(cenario.db, cenario.usuario))

    cenario.encerrar_sessoes.assert_awaited_once_with(cenario.db, cenario.usuario.id)
    cenario.db.commit.assert_awaited_once_with()
