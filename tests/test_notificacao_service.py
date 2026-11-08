"""Casos de notificações ainda não exercitados pelos testes de API."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, call
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import CanalNotificacao, RecomendacaoAvaliacao, StatusEnvioNotificacao
from app.models import NotificacaoResultado, ResultadoProposta
from app.services import notificacao


@pytest.fixture
def db():
    return MagicMock(spec=AsyncSession)


def resultado():
    return ResultadoProposta(
        homologacao_id=uuid4(),
        hackathon_id=uuid4(),
        submissao_id=uuid4(),
        equipe_id=uuid4(),
        aprovada=True,
    )


def aviso(usuario_id, submissao_id):
    return NotificacaoResultado(
        homologacao_id=uuid4(),
        hackathon_id=uuid4(),
        equipe_id=uuid4(),
        submissao_id=submissao_id,
        usuario_id=usuario_id,
        aprovada=True,
        mensagem="Proposta aprovada.",
        canal=CanalNotificacao.PLATAFORMA,
        status_envio=StatusEnvioNotificacao.ENVIADO,
        criado_em=datetime(2026, 11, 8, tzinfo=UTC),
    )


def test_sem_resultados_nao_consulta_integrantes_nem_confirma_transacao(db, monkeypatch):
    listar = AsyncMock()
    adicionar = Mock()
    monkeypatch.setattr(notificacao, "listar_membros", listar)
    monkeypatch.setattr(notificacao, "adicionar_notificacoes", adicionar)

    assert asyncio.run(notificacao.criar_notificacoes_do_resultado(db, [])) == 0

    listar.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_equipe_sem_integrantes_nao_gera_destinatarios(db, monkeypatch):
    proposta = resultado()
    listar = AsyncMock(return_value=[])
    adicionar = Mock()
    monkeypatch.setattr(notificacao, "listar_membros", listar)
    monkeypatch.setattr(notificacao, "adicionar_notificacoes", adicionar)

    assert asyncio.run(notificacao.criar_notificacoes_do_resultado(db, [proposta])) == 0

    listar.assert_awaited_once_with(db, proposta.equipe_id)
    assert all(not chamada.args[1] for chamada in adicionar.call_args_list)
    db.commit.assert_not_awaited()


def test_falha_ao_ler_segunda_equipe_nao_envia_lote_parcial_para_persistencia(db, monkeypatch):
    propostas = [resultado(), resultado()]
    falha = RuntimeError("Falha ao consultar a segunda equipe")
    listar = AsyncMock(side_effect=[[SimpleNamespace(usuario_id=uuid4())], falha])
    adicionar = Mock()
    monkeypatch.setattr(notificacao, "listar_membros", listar)
    monkeypatch.setattr(notificacao, "adicionar_notificacoes", adicionar)

    with pytest.raises(RuntimeError) as erro:
        asyncio.run(notificacao.criar_notificacoes_do_resultado(db, propostas))

    assert erro.value is falha
    assert listar.await_count == 2
    adicionar.assert_not_called()
    db.commit.assert_not_awaited()


def test_falha_ao_adicionar_notificacoes_e_propagada_ao_responsavel_pela_transacao(db, monkeypatch):
    falha = RuntimeError("Falha ao adicionar o lote")
    monkeypatch.setattr(
        notificacao, "listar_membros", AsyncMock(return_value=[SimpleNamespace(usuario_id=uuid4())])
    )
    monkeypatch.setattr(notificacao, "adicionar_notificacoes", Mock(side_effect=falha))

    with pytest.raises(RuntimeError) as erro:
        asyncio.run(notificacao.criar_notificacoes_do_resultado(db, [resultado()]))

    assert erro.value is falha
    db.commit.assert_not_awaited()
    db.rollback.assert_not_awaited()


def test_usuario_sem_notificacoes_nao_dispara_consultas_de_pareceres(db, monkeypatch):
    usuario_id = uuid4()
    listar = AsyncMock(return_value=[])
    pareceres = AsyncMock()
    monkeypatch.setattr(notificacao, "listar_notificacoes_do_usuario", listar)
    monkeypatch.setattr(notificacao, "listar_pareceres", pareceres)

    assert asyncio.run(notificacao.listar_minhas(db, usuario_id)) == []

    listar.assert_awaited_once_with(db, usuario_id)
    pareceres.assert_not_awaited()


@pytest.mark.parametrize("intercaladas", [False, True])
def test_pareceres_sao_consultados_uma_vez_por_proposta_sem_misturar_resultados(
    db, monkeypatch, intercaladas
):
    usuario_id, primeira, segunda = uuid4(), uuid4(), uuid4()
    propostas = [primeira, segunda, primeira] if intercaladas else [primeira, primeira]
    avisos = [aviso(usuario_id, id_) for id_ in propostas]
    comentarios = {primeira: "Parecer da primeira", segunda: "Parecer da segunda"}
    pareceres = AsyncMock(
        side_effect=lambda db, id_: [
            SimpleNamespace(
                comentarios=comentarios[id_], recomendacao=RecomendacaoAvaliacao.APROVACAO
            )
        ]
    )
    monkeypatch.setattr(
        notificacao, "listar_notificacoes_do_usuario", AsyncMock(return_value=avisos)
    )
    monkeypatch.setattr(notificacao, "listar_pareceres", pareceres)

    respostas = asyncio.run(notificacao.listar_minhas(db, usuario_id))

    assert [resposta.id for resposta in respostas] == [item.id for item in avisos]
    assert [resposta.pareceres[0].parecer for resposta in respostas] == [
        comentarios[id_] for id_ in propostas
    ]
    assert pareceres.await_args_list == [call(db, primeira)] + (
        [call(db, segunda)] if intercaladas else []
    )


def test_reuso_de_pareceres_fica_restrito_a_cada_chamada(db, monkeypatch):
    usuario_id, submissao_id = uuid4(), uuid4()
    pareceres = AsyncMock(
        side_effect=[
            [SimpleNamespace(comentarios="Versão anterior", recomendacao=None)],
            [SimpleNamespace(comentarios="Versão atualizada", recomendacao=None)],
        ]
    )
    monkeypatch.setattr(
        notificacao,
        "listar_notificacoes_do_usuario",
        AsyncMock(return_value=[aviso(usuario_id, submissao_id)]),
    )
    monkeypatch.setattr(notificacao, "listar_pareceres", pareceres)

    primeira = asyncio.run(notificacao.listar_minhas(db, usuario_id))
    segunda = asyncio.run(notificacao.listar_minhas(db, usuario_id))

    assert primeira[0].pareceres[0].parecer == "Versão anterior"
    assert segunda[0].pareceres[0].parecer == "Versão atualizada"
    assert pareceres.await_count == 2


def test_falha_na_consulta_de_parecer_nao_e_convertida_em_lista_vazia(db, monkeypatch):
    usuario_id = uuid4()
    falha = RuntimeError("Parecer temporariamente indisponível")
    monkeypatch.setattr(
        notificacao,
        "listar_notificacoes_do_usuario",
        AsyncMock(return_value=[aviso(usuario_id, uuid4())]),
    )
    monkeypatch.setattr(notificacao, "listar_pareceres", AsyncMock(side_effect=falha))

    with pytest.raises(RuntimeError) as erro:
        asyncio.run(notificacao.listar_minhas(db, usuario_id))

    assert erro.value is falha


def test_parecer_sem_comentario_ou_recomendacao_preserva_campos_ausentes(db, monkeypatch):
    submissao_id = uuid4()
    listar = AsyncMock(return_value=[SimpleNamespace(comentarios=None, recomendacao=None)])
    monkeypatch.setattr(notificacao, "listar_pareceres", listar)

    respostas = asyncio.run(notificacao.pareceres_da_proposta(db, submissao_id))

    assert [resposta.model_dump() for resposta in respostas] == [
        {"parecer": None, "recomendacao": None}
    ]
    listar.assert_awaited_once_with(db, submissao_id)
