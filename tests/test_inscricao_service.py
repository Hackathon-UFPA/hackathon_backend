"""Conclusão da inscrição e tratamento de falhas sem banco de dados."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import (
    FuncaoMembro,
    PapelUsuario,
    SituacaoEquipe,
    StatusHackathon,
    TipoProtocolo,
)
from app.const.inscricao import CodigoPendencia
from app.models import Equipe, Hackathon, MembroEquipe, Protocolo, Usuario
from app.services import inscricao
from app.services.homologacao import Avaliacao, Pendencia

AGORA = datetime(2026, 11, 7, 12, tzinfo=UTC)


@pytest.fixture
def cenario(monkeypatch):
    hackathon = Hackathon()
    equipe = Equipe(hackathon_id=hackathon.id)
    lider = Usuario(email="lider@example.com", papel=PapelUsuario.PARTICIPANTE)
    membro = MembroEquipe(
        equipe_id=equipe.id,
        hackathon_id=hackathon.id,
        usuario_id=lider.id,
        funcao=FuncaoMembro.LIDER,
    )
    protocolo = Protocolo(
        tipo=TipoProtocolo.INSCRICAO_EQUIPE,
        equipe_id=equipe.id,
        emitido_por=lider.id,
        numero="HK2026-000001",
        emitido_em=AGORA,
    )
    colaboradores = {
        "get_equipe_by_id": AsyncMock(return_value=equipe),
        "get_hackathon_by_id": AsyncMock(return_value=hackathon),
        "get_membro": AsyncMock(return_value=membro),
        "exigir_equipe_editavel": AsyncMock(),
        "avaliar": AsyncMock(return_value=Avaliacao(integrantes=[], convites_em_aberto=[])),
        "cancelar_convites_pendentes": AsyncMock(),
        "criar_protocolo": AsyncMock(return_value=protocolo),
        "reavaliar_homologacao": AsyncMock(),
    }
    for nome, substituto in colaboradores.items():
        monkeypatch.setattr(inscricao, nome, substituto)
    relogio = Mock(wraps=datetime)
    relogio.now.return_value = AGORA
    monkeypatch.setattr(inscricao, "datetime", relogio)
    return SimpleNamespace(
        db=MagicMock(spec=AsyncSession),
        hackathon=hackathon,
        equipe=equipe,
        lider=lider,
        protocolo=protocolo,
        **colaboradores,
    )


def concluir(cenario):
    return asyncio.run(inscricao.concluir(cenario.db, cenario.lider, cenario.equipe.id))


@pytest.mark.parametrize("homologar", [False, True])
def test_conclusao_emite_protocolo_e_informa_se_a_equipe_foi_homologada(cenario, homologar):
    if homologar:

        async def aprovar(db, equipe, hackathon):
            equipe.situacao = SituacaoEquipe.HOMOLOGADA
            equipe.homologada_em = AGORA

        cenario.reavaliar_homologacao.side_effect = aprovar

    resultado = concluir(cenario)

    esperado = SituacaoEquipe.HOMOLOGADA if homologar else SituacaoEquipe.AGUARDANDO_HOMOLOGACAO
    assert resultado.situacao == esperado
    assert resultado.equipe_id == cenario.equipe.id
    assert resultado.inscricao_concluida_em == AGORA
    assert resultado.protocolo.numero == "HK2026-000001"
    assert resultado.protocolo.numero in resultado.mensagem
    assert resultado.homologada_em == (AGORA if homologar else None)
    cenario.get_equipe_by_id.assert_awaited_once_with(
        cenario.db, cenario.equipe.id, para_atualizar=True
    )
    cenario.cancelar_convites_pendentes.assert_awaited_once_with(cenario.db, cenario.equipe.id)
    cenario.criar_protocolo.assert_awaited_once()
    db, protocolo = cenario.criar_protocolo.await_args.args
    assert db is cenario.db
    assert (protocolo.tipo, protocolo.equipe_id, protocolo.emitido_por) == (
        TipoProtocolo.INSCRICAO_EQUIPE,
        cenario.equipe.id,
        cenario.lider.id,
    )
    cenario.reavaliar_homologacao.assert_awaited_once_with(
        cenario.db, cenario.equipe, cenario.hackathon
    )
    cenario.db.commit.assert_awaited_once_with()
    cenario.db.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    "impedimento, status",
    [("sem-lider", 403), ("concluida", 409), ("fora-prazo", 409), ("pendencias", 409)],
)
def test_impedimentos_da_inscricao_nao_geram_protocolo_nem_gravacao(cenario, impedimento, status):
    if impedimento == "sem-lider":
        cenario.get_membro.return_value = None
    elif impedimento == "concluida":
        cenario.equipe.situacao = SituacaoEquipe.AGUARDANDO_HOMOLOGACAO
    elif impedimento == "fora-prazo":
        cenario.hackathon.status = StatusHackathon.INSCRICOES_ENCERRADAS
    else:
        cenario.avaliar.return_value.pendencias = [
            Pendencia(
                CodigoPendencia.TERMOS_NAO_ACEITOS,
                "Falta aceitar os termos.",
                bloqueia_conclusao=True,
            ),
            Pendencia(CodigoPendencia.COMPROVANTE_PENDENTE, "Comprovante em análise."),
        ]
    antes = cenario.equipe.model_dump()

    with pytest.raises(HTTPException) as erro:
        concluir(cenario)

    assert erro.value.status_code == status
    if impedimento == "pendencias":
        assert "Falta aceitar os termos." in erro.value.detail
        assert "Comprovante em análise." not in erro.value.detail
    assert cenario.equipe.model_dump() == antes
    cenario.cancelar_convites_pendentes.assert_not_awaited()
    cenario.criar_protocolo.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "etapa", ["cancelar_convites_pendentes", "criar_protocolo", "reavaliar_homologacao", "commit"]
)
def test_falha_na_conclusao_solicita_rollback_e_preserva_erro_original(cenario, etapa):
    falha = RuntimeError(f"Falha simulada em {etapa}")
    operacao = cenario.db.commit if etapa == "commit" else getattr(cenario, etapa)
    operacao.side_effect = falha

    with pytest.raises(RuntimeError) as erro:
        concluir(cenario)

    assert erro.value is falha
    cenario.db.rollback.assert_awaited_once_with()
    cenario.db.refresh.assert_not_awaited()
    if etapa != "commit":
        cenario.db.commit.assert_not_awaited()


def test_falha_na_reavaliacao_do_hackathon_solicita_rollback(cenario, monkeypatch):
    equipes = [cenario.equipe, Equipe(hackathon_id=cenario.hackathon.id)]
    listar = AsyncMock(return_value=equipes)
    monkeypatch.setattr(inscricao, "listar_equipes_para_homologacao", listar)
    falha = RuntimeError("Falha simulada na segunda equipe")
    cenario.reavaliar_homologacao.side_effect = [SituacaoEquipe.HOMOLOGADA, falha]

    with pytest.raises(RuntimeError) as erro:
        asyncio.run(inscricao.reavaliar_hackathon(cenario.db, cenario.hackathon.id))

    assert erro.value is falha
    assert cenario.reavaliar_homologacao.await_count == 2
    cenario.db.rollback.assert_awaited_once_with()
    cenario.db.commit.assert_not_awaited()
