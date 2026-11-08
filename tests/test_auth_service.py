"""Regras do cadastro e login com a persistência substituída por mocks."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import PapelUsuario, SituacaoConta
from app.models import Hackathon, Usuario
from app.schemas.auth import CadastroRequest
from app.services import auth

AGORA = datetime(2026, 11, 7, 12, tzinfo=UTC)
SENHA = "segredo123"


@pytest.fixture
def cenario(monkeypatch):
    class RelogioFixo(datetime):
        @classmethod
        def now(cls, tz=None):
            return AGORA.astimezone(tz) if tz else AGORA.replace(tzinfo=None)

    usuario = Usuario(
        email="participante@example.com",
        papel=PapelUsuario.PARTICIPANTE,
        senha_hash="hash-armazenado",
    )
    colaboradores = {
        "get_usuario_by_email": AsyncMock(return_value=usuario),
        "senha_confere": Mock(return_value=True),
        "gastar_tempo_de_verificacao": Mock(),
        "registrar_falha_de_login": AsyncMock(),
        "zerar_falhas_de_login": Mock(),
        "get_hackathon_com_inscricoes": AsyncMock(return_value=Hackathon()),
        "criar_usuario": AsyncMock(side_effect=lambda db, novo: novo),
        "criar_comprovante": AsyncMock(),
        "gerar_hash": Mock(return_value="hash-gerado"),
    }
    for nome, substituto in colaboradores.items():
        monkeypatch.setattr(auth, nome, substituto)
    monkeypatch.setattr(auth, "datetime", RelogioFixo)
    return SimpleNamespace(db=MagicMock(spec=AsyncSession), usuario=usuario, **colaboradores)


@pytest.fixture
def dados_cadastro():
    return CadastroRequest(
        nome="Maria da Silva",
        email="MARIA@example.com",
        senha=SENHA,
        instituicao="UFPA",
        curso="Sistemas de Informação",
        periodo=5,
        comprovante_url="https://example.com/comprovante.pdf",
    )


def autenticar(cenario):
    return asyncio.run(auth.autenticar(cenario.db, cenario.usuario.email, SENHA))


def test_cadastro_cria_conta_pendente_e_comprovante_na_mesma_sessao(cenario, dados_cadastro):
    usuario = asyncio.run(auth.cadastrar_participante(cenario.db, dados_cadastro))

    assert usuario.email == "maria@example.com"
    assert usuario.papel == PapelUsuario.PARTICIPANTE
    assert usuario.situacao_conta == SituacaoConta.PENDENTE
    assert usuario.ativo is True
    assert usuario.senha_hash == "hash-gerado"
    assert (usuario.nome, usuario.instituicao, usuario.curso, usuario.periodo) == (
        dados_cadastro.nome,
        dados_cadastro.instituicao,
        dados_cadastro.curso,
        dados_cadastro.periodo,
    )
    cenario.gerar_hash.assert_called_once_with(SENHA)
    cenario.get_hackathon_com_inscricoes.assert_awaited_once_with(cenario.db)
    cenario.criar_usuario.assert_awaited_once_with(cenario.db, usuario)
    cenario.criar_comprovante.assert_awaited_once()
    db, comprovante = cenario.criar_comprovante.await_args.args
    assert db is cenario.db
    assert comprovante.usuario_id == usuario.id
    assert comprovante.hackathon_id == cenario.get_hackathon_com_inscricoes.return_value.id
    assert comprovante.arquivo_url == str(dados_cadastro.comprovante_url)
    cenario.db.commit.assert_awaited_once_with()


def test_cadastro_sem_edicao_aberta_nao_cria_conta(cenario, dados_cadastro):
    cenario.get_hackathon_com_inscricoes.return_value = None

    with pytest.raises(HTTPException) as erro:
        asyncio.run(auth.cadastrar_participante(cenario.db, dados_cadastro))

    assert erro.value.status_code == 409
    cenario.gerar_hash.assert_not_called()
    cenario.criar_usuario.assert_not_awaited()
    cenario.criar_comprovante.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("etapa", ["criar_usuario", "criar_comprovante"])
def test_cadastro_nao_confirma_transacao_se_a_persistencia_falhar(cenario, dados_cadastro, etapa):
    falha = RuntimeError("Falha simulada na persistência")
    getattr(cenario, etapa).side_effect = falha

    with pytest.raises(RuntimeError) as erro:
        asyncio.run(auth.cadastrar_participante(cenario.db, dados_cadastro))

    assert erro.value is falha
    cenario.db.commit.assert_not_awaited()
    if etapa == "criar_usuario":
        cenario.criar_comprovante.assert_not_awaited()


@pytest.mark.parametrize("motivo", ["inexistente", "sem-senha", "desativada"])
def test_credenciais_indisponiveis_tem_resposta_generica_sem_alterar_conta(cenario, motivo):
    if motivo == "inexistente":
        cenario.get_usuario_by_email.return_value = None
    elif motivo == "sem-senha":
        cenario.usuario.senha_hash = None
    else:
        cenario.usuario.ativo = False

    with pytest.raises(HTTPException) as erro:
        autenticar(cenario)

    assert erro.value.status_code == 401
    assert erro.value.detail == "E-mail ou senha inválidos."
    assert erro.value.headers == {"WWW-Authenticate": "Bearer"}
    cenario.gastar_tempo_de_verificacao.assert_called_once_with(SENHA)
    cenario.senha_confere.assert_not_called()
    cenario.registrar_falha_de_login.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("segundos, retry_after", [(0.1, "1"), (59.2, "60"), (900, "901")])
def test_conta_bloqueada_informa_espera_sem_verificar_senha(cenario, segundos, retry_after):
    cenario.usuario.bloqueado_ate = AGORA + timedelta(seconds=segundos)

    with pytest.raises(HTTPException) as erro:
        autenticar(cenario)

    assert erro.value.status_code == 429
    assert erro.value.headers == {"Retry-After": retry_after}
    cenario.senha_confere.assert_not_called()
    cenario.registrar_falha_de_login.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


def test_senha_errada_registra_falha_antes_de_devolver_401(cenario, monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_TENTATIVAS", 3)
    monkeypatch.setattr(settings, "LOGIN_BLOQUEIO_MINUTOS", 7)
    cenario.senha_confere.return_value = False
    ordem = Mock()
    ordem.attach_mock(cenario.registrar_falha_de_login, "registrar")
    ordem.attach_mock(cenario.db.commit, "confirmar")

    with pytest.raises(HTTPException) as erro:
        autenticar(cenario)

    assert erro.value.status_code == 401
    assert erro.value.detail == "E-mail ou senha inválidos."
    cenario.senha_confere.assert_called_once_with(SENHA, cenario.usuario.senha_hash)
    cenario.registrar_falha_de_login.assert_awaited_once_with(
        cenario.db, cenario.usuario.id, 3, timedelta(minutes=7)
    )
    cenario.db.commit.assert_awaited_once_with()
    assert [chamada[0] for chamada in ordem.mock_calls] == ["registrar", "confirmar"]
    cenario.zerar_falhas_de_login.assert_not_called()


@pytest.mark.parametrize("situacao", list(SituacaoConta))
def test_login_correto_sem_falhas_retorna_usuario_sem_gravacao(cenario, situacao):
    cenario.usuario.situacao_conta = situacao

    assert autenticar(cenario) is cenario.usuario

    cenario.get_usuario_by_email.assert_awaited_once_with(cenario.db, cenario.usuario.email)
    cenario.senha_confere.assert_called_once_with(SENHA, cenario.usuario.senha_hash)
    cenario.zerar_falhas_de_login.assert_not_called()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("estado", ["falhas", "bloqueio-vencido", "limite-exato"])
def test_login_correto_limpa_historico_e_aceita_fim_do_bloqueio(cenario, estado):
    if estado == "falhas":
        cenario.usuario.tentativas_login = 2
    else:
        cenario.usuario.bloqueado_ate = (
            AGORA if estado == "limite-exato" else AGORA - timedelta(seconds=1)
        )

    assert autenticar(cenario) is cenario.usuario

    cenario.zerar_falhas_de_login.assert_called_once_with(cenario.db, cenario.usuario)
    cenario.db.commit.assert_awaited_once_with()
    cenario.registrar_falha_de_login.assert_not_awaited()
