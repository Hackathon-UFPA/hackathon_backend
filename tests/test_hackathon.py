"""Seleção da edição com inscrições abertas (RN06), usada no cadastro e reenvio."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon
from app.controllers.hackathon import get_hackathon_com_inscricoes
from app.models import Hackathon
from app.validations.inscricao import inscricoes_abertas
from tests.test_migrations import rodar
from tests.test_migrations import sql as sql_na_transacao


@pytest.mark.parametrize("edital_sem_fuso", [False, True])
@pytest.mark.parametrize("agora_sem_fuso", [False, True])
@pytest.mark.parametrize(
    "dias,esperado", [(-2, False), (-1, True), (0, True), (1, True), (2, False)]
)
def test_periodo_compativel_com_utc_com_ou_sem_fuso(
    edital_sem_fuso, agora_sem_fuso, dias, esperado
):
    referencia = datetime(2026, 10, 29, 12, tzinfo=UTC)
    inicio, fim = referencia - timedelta(days=1), referencia + timedelta(days=1)
    if edital_sem_fuso:
        inicio, fim = inicio.replace(tzinfo=None), fim.replace(tzinfo=None)
    agora = referencia + timedelta(days=dias)
    if agora_sem_fuso:
        agora = agora.replace(tzinfo=None)
    hackathon = Hackathon(inscricoes_inicio=inicio, inscricoes_fim=fim)

    assert inscricoes_abertas(hackathon, agora=agora) is esperado


def test_selecao_respeita_periodo_do_edital(hackathon_aberto, periodo_inscricoes):
    permitido = periodo_inscricoes(hackathon_aberto)

    async def verificar(conn):
        # Isola a seleção de edições preexistentes; rodar() desfaz esta alteração.
        await sql_na_transacao(
            conn,
            "UPDATE hackathon SET status = 'INSCRICOES_ENCERRADAS' WHERE id != :h",
            h=hackathon_aberto,
        )
        async with AsyncSession(bind=conn) as db:
            escolhido = await get_hackathon_com_inscricoes(db)
            assert (escolhido.id if escolhido else None) == (
                hackathon_aberto if permitido else None
            )

    rodar(verificar)


def test_selecao_preserva_ordem_e_ignora_edicoes_fora_do_periodo():
    async def verificar(conn):
        await sql_na_transacao(conn, "UPDATE hackathon SET status = 'INSCRICOES_ENCERRADAS'")
        agora = datetime.now(UTC)
        antes, depois = agora - timedelta(days=1), agora + timedelta(days=1)
        sem_inicio = Hackathon(nome="Sem data de início")
        antiga = Hackathon(nome="Aberta antiga", data_inicio=datetime(2099, 1, 1, tzinfo=UTC))
        recente = Hackathon(
            nome="Aberta recente",
            data_inicio=datetime(2100, 1, 1, tzinfo=UTC),
            inscricoes_inicio=antes,
            inscricoes_fim=depois,
        )
        encerrada = Hackathon(
            nome="Prazo encerrado",
            data_inicio=datetime(2101, 1, 1, tzinfo=UTC),
            inscricoes_fim=antes,
        )
        futura = Hackathon(
            nome="Inscrições futuras",
            data_inicio=datetime(2102, 1, 1, tzinfo=UTC),
            inscricoes_inicio=depois,
        )
        async with AsyncSession(bind=conn) as db:
            db.add_all([sem_inicio, antiga, recente, encerrada, futura])
            await db.flush()
            for esperada in [recente, antiga, sem_inicio]:
                escolhida = await get_hackathon_com_inscricoes(db)
                assert escolhida is not None
                assert escolhida.id == esperada.id
                esperada.status = StatusHackathon.INSCRICOES_ENCERRADAS
                db.add(esperada)
                await db.flush()
            assert await get_hackathon_com_inscricoes(db) is None

    rodar(verificar)
