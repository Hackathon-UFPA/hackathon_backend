"""BE-S5-05: gravação dos e-mails na fila (outbox) e as regras que o banco garante (RNF28)."""

import asyncio
import logging

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import TipoEmail
from app.services import email as servico
from app.services.email import enfileirar, link_front
from tests.helpers_email import emails_de, inserir_email, linha_do_email

CONTEXTO_CONVITE = {
    "nome": "Maria Souza",
    "equipe_nome": "Equipe Açaí",
    "lider_nome": "João Lima",
    "link": "https://hackathon.example/convites",
}


def com_sessao(funcao):
    """Executa `funcao(db)` com uma sessão própria. Quem usa decide commit ou rollback."""

    async def main():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                return await funcao(db)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def enfileirar_e_confirmar(email: str, **campos):
    async def acao(db):
        gravou = await enfileirar(
            db,
            campos.pop("tipo", TipoEmail.CONVITE_EQUIPE),
            destinatario_email=email,
            contexto=campos.pop("contexto", CONTEXTO_CONVITE),
            **campos,
        )
        await db.commit()
        return gravou

    return com_sessao(acao)


# --- Gravação ---


def test_enfileirar_grava_o_email_pendente_com_o_conteudo_pronto(sql, novo_email):
    email = novo_email()

    assert enfileirar_e_confirmar(email, destinatario_nome="Maria Souza", chave="teste:1") is True

    [linha] = emails_de(sql, email)
    assert linha["tipo"] == "CONVITE_EQUIPE"
    assert linha["status"] == "PENDENTE"
    assert linha["tentativas"] == 0
    assert linha["max_tentativas"] == settings.EMAIL_MAX_TENTATIVAS
    assert linha["destinatario_nome"] == "Maria Souza"
    assert linha["chave_idempotencia"] == "teste:1"
    assert linha["assunto"] == "Convite para participar de uma equipe no Hackathon UFPA"
    assert "João Lima convidou você" in linha["corpo_texto"]
    assert "https://hackathon.example/convites" in linha["corpo_html"]
    assert linha["enviado_em"] is None and linha["ultimo_erro"] is None
    # Já está pronto para o próximo ciclo do worker
    assert linha_do_email(sql, linha["id"])["segundos_ate_a_proxima"] <= 0


def test_destinatario_com_espacos_nas_pontas_e_aparado(sql, novo_email):
    email = novo_email()

    assert enfileirar_e_confirmar(f"  {email}  ") is True

    assert len(emails_de(sql, email)) == 1


def test_mesma_chave_nao_enfileira_o_aviso_duas_vezes(sql, novo_email):
    email = novo_email()

    assert enfileirar_e_confirmar(email, chave="convite:abc") is True
    assert enfileirar_e_confirmar(email, chave="convite:abc") is False

    assert len(emails_de(sql, email)) == 1


def test_sem_chave_cada_chamada_gera_um_email(sql, novo_email):
    email = novo_email()

    enfileirar_e_confirmar(email)
    enfileirar_e_confirmar(email)

    assert len(emails_de(sql, email)) == 2


def test_chaves_diferentes_para_o_mesmo_destinatario_geram_dois_emails(sql, novo_email):
    email = novo_email()

    enfileirar_e_confirmar(email, chave="convite:1")
    enfileirar_e_confirmar(email, chave="convite:2")

    assert len(emails_de(sql, email)) == 2


def test_so_existe_se_a_transacao_da_acao_for_confirmada(sql, novo_email):
    email = novo_email()

    async def acao_que_desiste(db):
        assert await enfileirar(
            db, TipoEmail.CONVITE_EQUIPE, destinatario_email=email, contexto=CONTEXTO_CONVITE
        )
        await db.rollback()

    com_sessao(acao_que_desiste)

    assert emails_de(sql, email) == []


def test_email_da_transacao_e_confirmado_junto_com_o_resto(sql, novo_email):
    email = novo_email()
    outro = novo_email()

    async def acao(db):
        await enfileirar(
            db, TipoEmail.CONVITE_EQUIPE, destinatario_email=email, contexto=CONTEXTO_CONVITE
        )
        await enfileirar(
            db, TipoEmail.CONVITE_EQUIPE, destinatario_email=outro, contexto=CONTEXTO_CONVITE
        )
        await db.commit()

    com_sessao(acao)

    assert len(emails_de(sql, email)) == 1 and len(emails_de(sql, outro)) == 1


# --- Falha ao enfileirar não derruba a ação principal ---


@pytest.mark.parametrize(
    "destinatario",
    ["", "   ", "sem-arroba", "@sem-usuario.com", "a@example.com\r\nBcc: b@example.com"],
    ids=["vazio", "espacos", "sem-arroba", "sem-usuario", "quebra-de-linha"],
)
def test_destinatario_invalido_nao_entra_na_fila_e_a_acao_segue(sql, caplog, destinatario):
    async def acao(db):
        with caplog.at_level(logging.ERROR, logger="app.services.email"):
            gravou = await enfileirar(
                db,
                TipoEmail.CONVITE_EQUIPE,
                destinatario_email=destinatario,
                contexto=CONTEXTO_CONVITE,
            )
        await db.commit()  # a transação de quem chamou continua utilizável
        return gravou

    assert com_sessao(acao) is False
    assert "Não foi possível enfileirar o e-mail" in caplog.text
    assert (
        sql(
            "SELECT count(*) AS n FROM emails_outbox WHERE destinatario_email = :d", d=destinatario
        )[0]["n"]
        == 0
    )


def test_template_com_contexto_incompleto_nao_entra_na_fila(sql, novo_email, caplog):
    email = novo_email()
    incompleto = {"nome": "Maria"}

    with caplog.at_level(logging.ERROR, logger="app.services.email"):
        assert enfileirar_e_confirmar(email, contexto=incompleto) is False

    assert emails_de(sql, email) == []
    assert "Faltam valores" in caplog.text


def test_erro_do_banco_ao_gravar_o_email_nao_perde_o_resto_da_transacao(
    sql, novo_email, monkeypatch
):
    anterior = novo_email()
    com_erro = novo_email()

    async def gravar_com_erro(db, valores):
        await db.exec(text("SELECT 1 / 0"))

    async def acao(db):
        await enfileirar(
            db, TipoEmail.CONVITE_EQUIPE, destinatario_email=anterior, contexto=CONTEXTO_CONVITE
        )
        monkeypatch.setattr(servico, "adicionar_email", gravar_com_erro)
        gravou = await enfileirar(
            db, TipoEmail.CONVITE_EQUIPE, destinatario_email=com_erro, contexto=CONTEXTO_CONVITE
        )
        await db.commit()
        return gravou

    assert com_sessao(acao) is False

    assert len(emails_de(sql, anterior)) == 1  # o que veio antes foi confirmado
    assert emails_de(sql, com_erro) == []


def test_link_do_front_nao_duplica_barras(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example.org/")

    assert link_front("/convites") == "https://app.example.org/convites"
    assert link_front("equipes/1") == "https://app.example.org/equipes/1"


# --- Garantias do banco ---


@pytest.mark.parametrize(
    ("campos", "constraint"),
    [
        ({"destinatario": "a@example.com\nBcc: b@example.com"}, "ck_emails_outbox_destinatario"),
        ({"destinatario": "sem-arroba"}, "ck_emails_outbox_destinatario"),
        ({"assunto": "Oi\r\nBcc: b@example.com"}, "ck_emails_outbox_assunto"),
        ({"tentativas": -1}, "ck_emails_outbox_tentativas"),
        ({"max_tentativas": 0}, "ck_emails_outbox_tentativas"),
        ({"com_corpo": False}, "ck_emails_outbox_corpo"),
        ({"status": "FALHA", "com_corpo": False}, "ck_emails_outbox_corpo"),
        ({"reservado_ate_em_segundos": 60}, "ck_emails_outbox_reserva"),
    ],
    ids=[
        "destinatario-com-quebra-de-linha",
        "destinatario-sem-arroba",
        "assunto-com-quebra-de-linha",
        "tentativas-negativas",
        "maximo-zero",
        "pendente-sem-corpo",
        "falha-sem-corpo",
        "reserva-fora-de-enviando",
    ],
)
def test_banco_recusa_email_invalido(sql, campos, constraint):
    destinatario = campos.pop("destinatario", "valido@example.com")

    with pytest.raises(IntegrityError, match=constraint):
        inserir_email(sql, destinatario, **campos)


def test_banco_recusa_enviado_sem_data_de_envio(sql):
    with pytest.raises(IntegrityError, match="ck_emails_outbox_enviado_em"):
        sql(
            "INSERT INTO emails_outbox (tipo, destinatario_email, assunto, status, max_tentativas)"
            " VALUES ('CONVITE_EQUIPE', 'valido@example.com', 'x', 'ENVIADO', 5)"
        )


def test_banco_recusa_chave_repetida(sql, novo_email):
    email = novo_email()
    inserir_email(sql, email, chave="dup:1")

    with pytest.raises(IntegrityError, match="uq_emails_outbox_chave"):
        inserir_email(sql, email, chave="dup:1")


def test_enviado_pode_ficar_sem_corpo(sql, novo_email):
    email = novo_email()

    inserir_email(sql, email, status="ENVIADO", com_corpo=False, tentativas=1)

    [linha] = emails_de(sql, email)
    assert linha["corpo_texto"] is None and linha["corpo_html"] is None
    assert linha["enviado_em"] is not None


def test_apagar_o_usuario_preserva_o_historico_do_email(sql, usuario_no_banco):
    usuario = usuario_no_banco(senha=None)
    email_id = sql(
        "INSERT INTO emails_outbox (tipo, destinatario_email, usuario_id, assunto, corpo_texto,"
        " corpo_html, max_tentativas) VALUES ('CONVITE_EQUIPE', :e, :u, 'x', 't', 'h', 5)"
        " RETURNING id",
        e=usuario["email"],
        u=usuario["id"],
    )[0]["id"]

    sql("DELETE FROM usuarios WHERE id = :u", u=usuario["id"])

    assert linha_do_email(sql, email_id)["usuario_id"] is None
