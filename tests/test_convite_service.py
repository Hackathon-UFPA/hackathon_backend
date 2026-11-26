"""Envio e aceite de convites com os controllers substituídos por mocks."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FuncaoMembro, PapelUsuario, StatusConvite, TipoIntegrante
from app.models import Convite, Equipe, Hackathon, MembroEquipe, Usuario
from app.schemas.convite import ConviteEnvio
from app.services import convite as service
from app.services.token_usuario import hash_do_token

pytestmark = pytest.mark.unit

AGORA = datetime(2026, 11, 7, 12, tzinfo=UTC)


@pytest.fixture
def cenario(monkeypatch):
    hackathon = Hackathon()
    equipe = Equipe(hackathon_id=hackathon.id)
    lider = Usuario(email="lider@example.com", papel=PapelUsuario.PARTICIPANTE)
    usuario = Usuario(email="pessoa@example.com", papel=PapelUsuario.PARTICIPANTE)
    convite = Convite(
        equipe_id=equipe.id, nome="Pessoa", email="PESSOA@example.com", convidado_por=lider.id
    )
    membro_lider = MembroEquipe(
        equipe_id=equipe.id,
        hackathon_id=hackathon.id,
        usuario_id=lider.id,
        funcao=FuncaoMembro.LIDER,
    )
    colaboradores = {
        "get_equipe_by_id": AsyncMock(return_value=equipe),
        "get_hackathon_by_id": AsyncMock(return_value=hackathon),
        "get_membro": AsyncMock(
            side_effect=lambda db, equipe_id, usuario_id: (
                membro_lider if usuario_id == lider.id else None
            )
        ),
        "get_usuario_by_email": AsyncMock(return_value=None),
        "get_membro_no_hackathon": AsyncMock(return_value=None),
        "contar_membros": AsyncMock(return_value=3),
        "contar_pendentes": AsyncMock(return_value=1),
        "criar_convite": AsyncMock(side_effect=lambda db, novo: novo),
        "get_convite_by_id": AsyncMock(return_value=convite),
        "exigir_equipe_editavel": AsyncMock(),
        "validar_termos_aceitos": AsyncMock(return_value=[uuid4(), uuid4()]),
        "registrar_aceites": AsyncMock(),
        "adicionar_membro": Mock(),
        "avisar_convite": AsyncMock(),
        "notificar_convite": AsyncMock(),
        "notificar_resposta_convite": AsyncMock(),
        "_agora_utc": Mock(return_value=AGORA),
    }
    for nome, substituto in colaboradores.items():
        monkeypatch.setattr(service, nome, substituto)
    return SimpleNamespace(
        db=MagicMock(spec=AsyncSession),
        hackathon=hackathon,
        equipe=equipe,
        lider=lider,
        usuario=usuario,
        convite=convite,
        **colaboradores,
    )


def enviar(cenario):
    dados = ConviteEnvio(nome="Pessoa", email="PESSOA@example.com")
    return asyncio.run(service.enviar_convite(cenario.db, cenario.lider, cenario.equipe.id, dados))


def aceitar(cenario):
    return asyncio.run(
        service.aceitar_convite(
            cenario.db,
            cenario.usuario,
            cenario.convite.id,
            cenario.validar_termos_aceitos.return_value,
        )
    )


@pytest.mark.parametrize("cadastrado", [False, True])
def test_envio_normaliza_email_e_vincula_usuario_quando_existente(cenario, cadastrado):
    cenario.get_usuario_by_email.return_value = cenario.usuario if cadastrado else None

    resultado = enviar(cenario)

    assert resultado.email == "pessoa@example.com"
    assert resultado.equipe_id == cenario.equipe.id
    assert resultado.convidado_por == cenario.lider.id
    assert resultado.usuario_id == (cenario.usuario.id if cadastrado else None)
    assert resultado.tipo_integrante == TipoIntegrante.ESTUDANTE
    cenario.get_equipe_by_id.assert_awaited_once_with(
        cenario.db, cenario.equipe.id, para_atualizar=True
    )
    cenario.criar_convite.assert_awaited_once_with(cenario.db, resultado)
    *_, token = cenario.avisar_convite.await_args.args
    if cadastrado:
        assert token is None
        assert resultado.token_hash is None
    else:
        assert resultado.token_hash == hash_do_token(token)
        assert resultado.token_expira_em > AGORA
    cenario.notificar_convite.assert_awaited_once_with(
        cenario.db, resultado, cenario.equipe, cenario.lider
    )
    cenario.db.commit.assert_awaited_once_with()
    cenario.db.refresh.assert_awaited_once_with(resultado)


@pytest.mark.parametrize("membros, pendentes", [(3, 2), (5, 0)])
def test_envio_conta_convites_pendentes_para_impedir_excesso_de_integrantes(
    cenario, membros, pendentes
):
    cenario.contar_membros.return_value = membros
    cenario.contar_pendentes.return_value = pendentes

    with pytest.raises(HTTPException) as erro:
        enviar(cenario)

    assert erro.value.status_code == 409
    assert "máximo de 5" in erro.value.detail
    cenario.criar_convite.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("tem_vinculo", [False, True])
def test_envio_exige_funcao_de_lider(cenario, tem_vinculo):
    cenario.get_membro.side_effect = None
    cenario.get_membro.return_value = (
        MembroEquipe(
            equipe_id=cenario.equipe.id,
            hackathon_id=cenario.hackathon.id,
            usuario_id=cenario.lider.id,
            funcao=FuncaoMembro.DESENVOLVEDOR,
        )
        if tem_vinculo
        else None
    )

    with pytest.raises(HTTPException) as erro:
        enviar(cenario)

    assert erro.value.status_code == 403
    cenario.criar_convite.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize("motivo", ["inexistente", "outro-destinatario"])
def test_aceite_nao_revela_convite_ausente_ou_de_outra_pessoa(cenario, motivo):
    if motivo == "inexistente":
        cenario.get_convite_by_id.return_value = None
    else:
        cenario.convite.email = "outra@example.com"

    with pytest.raises(HTTPException) as erro:
        aceitar(cenario)

    assert erro.value.status_code == 404
    assert erro.value.detail == "Convite não encontrado."
    cenario.get_equipe_by_id.assert_not_awaited()
    cenario.adicionar_membro.assert_not_called()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "status", [StatusConvite.ACEITO, StatusConvite.RECUSADO, StatusConvite.CANCELADO]
)
def test_convite_respondido_nao_pode_ser_aceito(cenario, status):
    cenario.convite.status = status

    with pytest.raises(HTTPException) as erro:
        aceitar(cenario)

    assert erro.value.status_code == 409
    cenario.adicionar_membro.assert_not_called()
    cenario.db.commit.assert_not_awaited()


def test_aceite_registra_termos_integrante_e_resposta_na_mesma_sessao(cenario):
    resultado = aceitar(cenario)

    assert resultado is cenario.convite
    assert resultado.status == StatusConvite.ACEITO
    assert resultado.usuario_id == cenario.usuario.id
    assert resultado.respondido_em == AGORA
    cenario.registrar_aceites.assert_awaited_once_with(
        cenario.db, cenario.usuario.id, cenario.validar_termos_aceitos.return_value
    )
    cenario.adicionar_membro.assert_called_once()
    db, membro = cenario.adicionar_membro.call_args.args
    assert db is cenario.db
    assert (membro.usuario_id, membro.equipe_id, membro.hackathon_id) == (
        cenario.usuario.id,
        cenario.equipe.id,
        cenario.hackathon.id,
    )
    cenario.db.commit.assert_awaited_once_with()
    cenario.db.refresh.assert_awaited_once_with(cenario.convite)


@pytest.mark.parametrize("etapa", ["validar_termos_aceitos", "registrar_aceites"])
def test_falha_nos_termos_nao_adiciona_integrante_nem_confirma_aceite(cenario, etapa):
    falha = RuntimeError("Falha simulada nos termos")
    getattr(cenario, etapa).side_effect = falha

    with pytest.raises(RuntimeError) as erro:
        aceitar(cenario)

    assert erro.value is falha
    assert cenario.convite.status == StatusConvite.PENDENTE
    cenario.adicionar_membro.assert_not_called()
    cenario.db.commit.assert_not_awaited()


def test_conflito_de_vinculo_no_commit_exige_rollback_e_retorna_409(cenario):
    cenario.db.commit.side_effect = IntegrityError(
        "INSERT", {}, Exception('unique constraint "uq_membros_equipe_hackathon_usuario"')
    )

    with pytest.raises(HTTPException) as erro:
        aceitar(cenario)

    assert erro.value.status_code == 409
    assert "já faz parte de uma equipe" in erro.value.detail
    cenario.db.rollback.assert_awaited_once_with()
    cenario.db.refresh.assert_not_awaited()


def test_falha_ao_criar_convite_nao_confirma_transacao(cenario):
    cenario.criar_convite.side_effect = RuntimeError("Falha simulada ao persistir convite")

    with pytest.raises(RuntimeError, match="persistir convite"):
        enviar(cenario)

    cenario.db.commit.assert_not_awaited()
    cenario.db.refresh.assert_not_awaited()
