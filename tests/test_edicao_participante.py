import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, StatusHackathon
from app.models import Hackathon, Usuario
from app.services import edicao_participante

pytestmark = pytest.mark.unit


@pytest.fixture
def db():
    return MagicMock(spec=AsyncSession)


@pytest.mark.parametrize("existe", [False, True])
def test_sem_id_usa_a_selecao_legada(db, monkeypatch, existe):
    edicao = Hackathon() if existe else None
    selecionar = AsyncMock(return_value=edicao)
    obter = AsyncMock()
    monkeypatch.setattr(edicao_participante, "get_hackathon_com_inscricoes", selecionar)
    monkeypatch.setattr(edicao_participante, "obter_acessivel", obter)

    if existe:
        assert asyncio.run(edicao_participante.resolver_edicao(db, None)) is edicao
    else:
        with pytest.raises(HTTPException) as erro:
            asyncio.run(edicao_participante.resolver_edicao(db, None))
        assert erro.value.status_code == 409

    selecionar.assert_awaited_once_with(db)
    obter.assert_not_awaited()


@pytest.mark.parametrize(
    ("status", "exige_inscricoes", "permitido"),
    [
        (StatusHackathon.INSCRICOES, True, True),
        (StatusHackathon.FINALIZADO, True, False),
        (StatusHackathon.FINALIZADO, False, True),
    ],
)
def test_id_explicito_consulta_edicao_autorizada(
    db, monkeypatch, status, exige_inscricoes, permitido
):
    usuario = Usuario(email="ana@example.com", papel=PapelUsuario.PARTICIPANTE)
    edicao = Hackathon(status=status)
    obter = AsyncMock(return_value=edicao)
    selecionar = AsyncMock()
    monkeypatch.setattr(edicao_participante, "obter_acessivel", obter)
    monkeypatch.setattr(edicao_participante, "get_hackathon_com_inscricoes", selecionar)

    operacao = edicao_participante.resolver_edicao(
        db, edicao.id, exigir_inscricoes=exige_inscricoes, usuario=usuario
    )
    if permitido:
        assert asyncio.run(operacao) is edicao
    else:
        with pytest.raises(HTTPException) as erro:
            asyncio.run(operacao)
        assert erro.value.status_code == 409

    obter.assert_awaited_once_with(db, edicao.id, usuario)
    selecionar.assert_not_awaited()


def test_edicao_inacessivel_preserva_404_sem_revelar_o_prazo(db, monkeypatch):
    falha = HTTPException(404, "Edição não encontrada")
    monkeypatch.setattr(edicao_participante, "obter_acessivel", AsyncMock(side_effect=falha))
    selecionar = AsyncMock()
    monkeypatch.setattr(edicao_participante, "get_hackathon_com_inscricoes", selecionar)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(edicao_participante.resolver_edicao(db, uuid4()))

    assert erro.value is falha
    selecionar.assert_not_awaited()
