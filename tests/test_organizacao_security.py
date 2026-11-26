import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.models import ComprovanteVinculo, Equipe, Hackathon, Submissao, Tema, Usuario
from app.security import organizacao

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("mesma_organizacao", [False, True])
def test_gestor_do_hackathon_valida_diretamente_a_edicao(mesma_organizacao):
    usuario = Usuario(
        email="gestor@example.com", papel=PapelUsuario.ORGANIZADOR, organizacao_id=uuid4()
    )
    edicao = Hackathon(organizacao_id=usuario.organizacao_id if mesma_organizacao else uuid4())
    db = MagicMock(spec=AsyncSession)
    db.get.return_value = edicao
    verificar = organizacao.gestor_do_hackathon(PapelUsuario.ORGANIZADOR)

    if mesma_organizacao:
        assert asyncio.run(verificar(edicao.id, db, usuario)) is usuario
    else:
        with pytest.raises(HTTPException) as erro:
            asyncio.run(verificar(edicao.id, db, usuario))
        assert erro.value.status_code == 403
    db.get.assert_awaited_once_with(Hackathon, edicao.id)


@pytest.mark.parametrize(
    ("modelo", "dependencia"),
    [
        (Tema, organizacao.gestor_do_tema),
        (Submissao, organizacao.gestor_da_proposta),
        (ComprovanteVinculo, organizacao.conferente_do_comprovante),
        (Equipe, organizacao.gestor_da_equipe),
    ],
)
@pytest.mark.parametrize("estado", ["mesma", "outra", "dev", "legado", "sem-recurso", "sem-edicao"])
def test_dependencia_confere_a_organizacao_da_edicao_do_recurso(modelo, dependencia, estado):
    db = MagicMock(spec=AsyncSession)
    recurso_id = uuid4()
    organizacao_id = None if estado == "legado" else uuid4()
    usuario = Usuario(
        email="gestor@example.com",
        papel=PapelUsuario.DEV if estado == "dev" else PapelUsuario.ORGANIZADOR,
        organizacao_id=organizacao_id,
    )
    edicao = Hackathon(organizacao_id=uuid4() if estado in {"outra", "dev"} else organizacao_id)
    recurso = SimpleNamespace(hackathon_id=edicao.id)
    db.get.side_effect = (
        [None] if estado == "sem-recurso" else [recurso, None if estado == "sem-edicao" else edicao]
    )
    verificar = dependencia(PapelUsuario.ORGANIZADOR)

    if estado == "outra":
        with pytest.raises(HTTPException) as erro:
            asyncio.run(verificar(recurso_id, db, usuario))
        assert erro.value.status_code == 403
    else:
        assert asyncio.run(verificar(recurso_id, db, usuario)) is usuario

    buscas = [call(modelo, recurso_id)]
    removidos_da_sessao = []
    if estado != "sem-recurso":
        buscas.append(call(Hackathon, edicao.id))
        removidos_da_sessao.append(call(recurso))
        if estado != "sem-edicao":
            removidos_da_sessao.append(call(edicao))
    assert db.get.await_args_list == buscas
    assert db.expunge.call_args_list == removidos_da_sessao


@pytest.mark.parametrize("estado", ["mesma", "outra", "dev", "sem-mentor"])
def test_gestor_de_mentor_responde_404_para_mentor_de_outra_organizacao(estado):
    db = MagicMock(spec=AsyncSession)
    usuario = Usuario(
        email="gestor@example.com",
        papel=PapelUsuario.DEV if estado == "dev" else PapelUsuario.ORGANIZADOR,
        organizacao_id=uuid4(),
    )
    mentor = Usuario(
        email="mentor@example.com",
        papel=PapelUsuario.MENTOR,
        organizacao_id=usuario.organizacao_id if estado == "mesma" else uuid4(),
    )
    db.get.return_value = None if estado == "sem-mentor" else mentor
    verificar = organizacao.gestor_do_mentor(PapelUsuario.ORGANIZADOR)

    if estado == "outra":
        with pytest.raises(HTTPException) as erro:
            asyncio.run(verificar(mentor.id, db, usuario))
        assert erro.value.status_code == 404
    else:
        assert asyncio.run(verificar(mentor.id, db, usuario)) is usuario
    db.get.assert_awaited_once_with(Usuario, mentor.id)


@pytest.mark.parametrize("estado", ["mesma", "outra", "inexistente", "sem-id"])
def test_atribuicao_consulta_mentor_quando_ha_id(estado):
    db = MagicMock(spec=AsyncSession)
    usuario = Usuario(
        email="gestor@example.com", papel=PapelUsuario.ORGANIZADOR, organizacao_id=uuid4()
    )
    mentor = Usuario(
        email="mentor@example.com",
        papel=PapelUsuario.MENTOR,
        organizacao_id=uuid4() if estado == "outra" else usuario.organizacao_id,
    )
    db.get.return_value = None if estado == "inexistente" else mentor
    mentor_id = None if estado == "sem-id" else mentor.id
    operacao = organizacao.garantir_mentor_da_organizacao(db, usuario, mentor_id)

    if estado == "outra":
        with pytest.raises(HTTPException) as erro:
            asyncio.run(operacao)
        assert erro.value.status_code == 404
    else:
        asyncio.run(operacao)

    if mentor_id is None:
        db.get.assert_not_awaited()
    else:
        db.get.assert_awaited_once_with(Usuario, mentor_id)
