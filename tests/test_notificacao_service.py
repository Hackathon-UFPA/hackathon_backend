import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, call
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import CanalNotificacao, StatusEnvioNotificacao, TipoNotificacao
from app.models import Notificacao, NotificacaoResultado, ResultadoProposta
from app.services import notificacao

pytestmark = pytest.mark.unit


@pytest.fixture
def db():
    return MagicMock(spec=AsyncSession)


def resultado_proposta():
    return ResultadoProposta(
        homologacao_id=uuid4(),
        hackathon_id=uuid4(),
        submissao_id=uuid4(),
        equipe_id=uuid4(),
        aprovada=True,
    )


def aviso_de_resultado(usuario_id, submissao_id):
    criado_em = datetime(2026, 11, 8, tzinfo=UTC)
    aviso = NotificacaoResultado(
        homologacao_id=uuid4(),
        hackathon_id=uuid4(),
        equipe_id=uuid4(),
        submissao_id=submissao_id,
        usuario_id=usuario_id,
        aprovada=True,
        mensagem="Proposta aprovada.",
        canal=CanalNotificacao.PLATAFORMA,
        status_envio=StatusEnvioNotificacao.ENVIADO,
        criado_em=criado_em,
    )
    central = Notificacao(
        usuario_id=usuario_id,
        tipo=TipoNotificacao.RESULTADO,
        titulo="Resultado do hackathon",
        mensagem=aviso.mensagem,
        chave_idempotencia=str(aviso.id),
        notificacao_resultado_id=aviso.id,
        criado_em=criado_em,
    )
    return central, aviso


def test_pagina_vazia_preserva_total_do_filtro_sem_buscar_pareceres(db, monkeypatch):
    usuario = uuid4()
    listar = AsyncMock(return_value=[])
    contar = AsyncMock(return_value=3)
    pareceres = AsyncMock()
    monkeypatch.setattr(notificacao, "listar_notificacoes_do_usuario", listar)
    monkeypatch.setattr(notificacao, "contar_notificacoes", contar)
    monkeypatch.setattr(notificacao, "listar_pareceres", pareceres)

    resposta = asyncio.run(
        notificacao.listar_minhas(
            db, usuario, lida=False, tipo=TipoNotificacao.RESULTADO, limite=2, deslocamento=4
        )
    )

    assert resposta == ([], 3)
    listar.assert_awaited_once_with(
        db, usuario, lida=False, tipo=TipoNotificacao.RESULTADO, limite=2, deslocamento=4
    )
    contar.assert_awaited_once_with(db, usuario, lida=False, tipo=TipoNotificacao.RESULTADO)
    pareceres.assert_not_awaited()


def test_pareceres_sao_reutilizados_por_proposta_sem_misturar_resultados(db, monkeypatch):
    usuario, primeira, segunda = uuid4(), uuid4(), uuid4()
    linhas = [aviso_de_resultado(usuario, id_) for id_ in [primeira, segunda, primeira]]
    monkeypatch.setattr(
        notificacao, "listar_notificacoes_do_usuario", AsyncMock(return_value=linhas)
    )
    monkeypatch.setattr(notificacao, "contar_notificacoes", AsyncMock(return_value=3))
    pareceres = AsyncMock(
        side_effect=[
            [SimpleNamespace(comentarios="Primeiro parecer", recomendacao=None)],
            [SimpleNamespace(comentarios="Segundo parecer", recomendacao=None)],
        ]
    )
    monkeypatch.setattr(notificacao, "listar_pareceres", pareceres)

    respostas, total = asyncio.run(notificacao.listar_minhas(db, usuario))

    assert total == 3
    assert [item.notificacao_id for item in respostas] == [central.id for central, _ in linhas]
    assert [item.pareceres[0].parecer for item in respostas] == [
        "Primeiro parecer",
        "Segundo parecer",
        "Primeiro parecer",
    ]
    assert pareceres.await_args_list == [call(db, primeira), call(db, segunda)]


def test_nova_listagem_busca_parecer_atualizado(db, monkeypatch):
    usuario, submissao = uuid4(), uuid4()
    monkeypatch.setattr(
        notificacao,
        "listar_notificacoes_do_usuario",
        AsyncMock(return_value=[aviso_de_resultado(usuario, submissao)]),
    )
    monkeypatch.setattr(notificacao, "contar_notificacoes", AsyncMock(return_value=1))
    pareceres = AsyncMock(
        side_effect=[
            [SimpleNamespace(comentarios="Parecer anterior", recomendacao=None)],
            [SimpleNamespace(comentarios="Parecer atualizado", recomendacao=None)],
        ]
    )
    monkeypatch.setattr(notificacao, "listar_pareceres", pareceres)

    primeira, _ = asyncio.run(notificacao.listar_minhas(db, usuario))
    segunda, _ = asyncio.run(notificacao.listar_minhas(db, usuario))

    assert primeira[0].pareceres[0].parecer == "Parecer anterior"
    assert segunda[0].pareceres[0].parecer == "Parecer atualizado"
    assert pareceres.await_args_list == [call(db, submissao), call(db, submissao)]


def test_falha_ao_ler_segunda_equipe_nao_persiste_lote_parcial(db, monkeypatch):
    primeira, segunda = resultado_proposta(), resultado_proposta()
    falha = RuntimeError("Falha ao consultar integrantes")
    listar = AsyncMock(side_effect=[[SimpleNamespace(usuario_id=uuid4())], falha])
    adicionar = Mock()
    adicionar_centrais = Mock()
    monkeypatch.setattr(notificacao, "listar_membros", listar)
    monkeypatch.setattr(notificacao, "adicionar_notificacoes", adicionar)
    monkeypatch.setattr(notificacao, "adicionar_notificacoes_centrais", adicionar_centrais)

    with pytest.raises(RuntimeError) as erro:
        asyncio.run(notificacao.criar_notificacoes_do_resultado(db, [primeira, segunda]))

    assert erro.value is falha
    assert listar.await_args_list == [call(db, primeira.equipe_id), call(db, segunda.equipe_id)]
    adicionar.assert_not_called()
    adicionar_centrais.assert_not_called()
    db.flush.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_avisos_da_central_sao_adicionados_depois_do_flush_dos_avisos_de_resultado(db, monkeypatch):
    proposta = resultado_proposta()
    usuario = uuid4()
    monkeypatch.setattr(
        notificacao, "listar_membros", AsyncMock(return_value=[SimpleNamespace(usuario_id=usuario)])
    )
    operacoes = Mock()
    operacoes.attach_mock(db.flush, "flush")
    monkeypatch.setattr(notificacao, "adicionar_notificacoes", operacoes.adicionar_resultado)
    monkeypatch.setattr(notificacao, "adicionar_notificacoes_centrais", operacoes.adicionar_central)

    assert asyncio.run(notificacao.criar_notificacoes_do_resultado(db, [proposta])) == 1

    (aviso,) = operacoes.adicionar_resultado.call_args.args[1]
    (central,) = operacoes.adicionar_central.call_args.args[1]
    assert operacoes.mock_calls == [
        call.adicionar_resultado(db, [aviso]),
        call.flush(),
        call.adicionar_central(db, [central]),
    ]
    assert central.usuario_id == aviso.usuario_id == usuario
    assert central.notificacao_resultado_id == aviso.id
    assert central.referencia_id == proposta.homologacao_id
    db.flush.assert_awaited_once_with()
    db.commit.assert_not_awaited()
