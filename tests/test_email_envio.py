"""BE-S5-05: envio da fila pelo worker, com tentativas e rastreamento de falhas (RNF28).

O provedor é sempre o falso (`ProvedorMemoria`): nenhum teste envia e-mail de verdade.
"""

import asyncio

from sqlalchemy import text

from app.const.config import settings
from app.controllers.email_outbox import reservar_emails
from app.integrations.email import ErroEnvioPermanente, ErroEnvioTemporario, ProvedorMemoria
from app.services.email_envio import espera_em_segundos
from tests.helpers_email import inserir_email, linha_do_email
from tests.test_email_fila import com_sessao

DESTINATARIO = "envio@testes.com"


# --- Espera entre tentativas ---


def test_espera_dobra_a_cada_tentativa_e_para_no_teto(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKOFF_BASE_SEGUNDOS", 30)
    monkeypatch.setattr(settings, "EMAIL_BACKOFF_MAX_SEGUNDOS", 1800)

    assert [espera_em_segundos(n) for n in range(1, 9)] == [30, 60, 120, 240, 480, 960, 1800, 1800]


# --- Envio com sucesso ---


def test_envio_com_sucesso_marca_enviado_e_apaga_o_corpo(sql, processar):
    email_id = inserir_email(sql, DESTINATARIO, assunto="Convite de teste")
    provedor = ProvedorMemoria()

    resumo = processar(provedor)

    assert (resumo.enviados, resumo.reagendados, resumo.falhas) == (1, 0, 0)
    [mensagem] = provedor.enviadas
    assert mensagem.destinatario == DESTINATARIO
    assert mensagem.assunto == "Convite de teste"
    assert mensagem.texto == "Texto do e-mail" and mensagem.html == "<p>Html do e-mail</p>"
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "ENVIADO"
    assert linha["tentativas"] == 1
    assert linha["enviado_em"] is not None
    assert linha["provedor_mensagem_id"] == "memoria-1"
    assert linha["corpo_texto"] is None and linha["corpo_html"] is None
    assert linha["reservado_ate"] is None and linha["ultimo_erro"] is None


def test_email_enviado_nao_e_enviado_de_novo(sql, processar):
    inserir_email(sql, DESTINATARIO)
    provedor = ProvedorMemoria()

    processar(provedor)
    segundo = processar(provedor)

    assert segundo.total == 0
    assert len(provedor.enviadas) == 1


def test_fila_vazia_nao_chama_o_provedor(processar):
    provedor = ProvedorMemoria()

    assert processar(provedor).total == 0
    assert provedor.tentativas == 0


# --- Falhas temporárias e tentativas ---


def test_falha_temporaria_reagenda_com_espera_e_guarda_o_motivo(sql, processar):
    email_id = inserir_email(sql, DESTINATARIO)
    provedor = ProvedorMemoria(falhas=[ErroEnvioTemporario("Servidor fora do ar")])

    resumo = processar(provedor)

    assert (resumo.enviados, resumo.reagendados, resumo.falhas) == (0, 1, 0)
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "PENDENTE"
    assert linha["tentativas"] == 1
    assert linha["ultimo_erro"] == "Servidor fora do ar"
    assert linha["reservado_ate"] is None
    assert linha["corpo_texto"] is not None  # ainda vai precisar do corpo
    esperado = settings.EMAIL_BACKOFF_BASE_SEGUNDOS
    assert esperado - 5 <= float(linha["segundos_ate_a_proxima"]) <= esperado


def test_nao_tenta_de_novo_antes_da_hora(sql, processar):
    inserir_email(sql, DESTINATARIO)
    provedor = ProvedorMemoria(falhas=[ErroEnvioTemporario("fora do ar")])
    processar(provedor)

    segundo = processar(provedor)

    assert segundo.total == 0
    assert provedor.tentativas == 1


def test_a_espera_dobra_na_segunda_falha(sql, processar):
    email_id = inserir_email(sql, DESTINATARIO, tentativas=1, proxima_em_segundos=-1)
    provedor = ProvedorMemoria(falhas=[ErroEnvioTemporario("fora do ar")])

    processar(provedor)

    linha = linha_do_email(sql, email_id)
    assert linha["tentativas"] == 2
    esperado = settings.EMAIL_BACKOFF_BASE_SEGUNDOS * 2
    assert esperado - 5 <= float(linha["segundos_ate_a_proxima"]) <= esperado


def test_depois_da_espera_envia_e_nao_perde_o_aviso(sql, processar):
    email_id = inserir_email(sql, DESTINATARIO)
    provedor = ProvedorMemoria(falhas=[ErroEnvioTemporario("fora do ar")])
    processar(provedor)
    sql(
        "UPDATE emails_outbox SET proxima_tentativa_em = (now() AT TIME ZONE 'utc')"
        " - interval '1 second' WHERE id = :id",
        id=email_id,
    )

    resumo = processar(provedor)

    assert resumo.enviados == 1
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "ENVIADO" and linha["tentativas"] == 2
    assert linha["ultimo_erro"] is None  # o erro antigo não fica em um e-mail entregue


def test_esgotadas_as_tentativas_o_email_vai_para_falha(sql, processar):
    email_id = inserir_email(sql, DESTINATARIO, tentativas=1, max_tentativas=2)
    provedor = ProvedorMemoria(falhas=[ErroEnvioTemporario("ainda fora do ar")])

    resumo = processar(provedor)

    assert (resumo.reagendados, resumo.falhas) == (0, 1)
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "FALHA" and linha["tentativas"] == 2
    assert linha["ultimo_erro"] == "ainda fora do ar"
    assert linha["corpo_texto"] is not None  # preservado para o reenvio manual
    assert processar(provedor).total == 0  # e o worker não insiste


def test_erro_permanente_vai_direto_para_falha_sem_gastar_as_tentativas(sql, processar):
    email_id = inserir_email(sql, DESTINATARIO)
    provedor = ProvedorMemoria(falhas=[ErroEnvioPermanente("Destinatário recusado (550)")])

    resumo = processar(provedor)

    assert (resumo.reagendados, resumo.falhas) == (0, 1)
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "FALHA" and linha["tentativas"] == 1
    assert linha["ultimo_erro"] == "Destinatário recusado (550)"


def test_erro_inesperado_do_provedor_e_tratado_como_temporario(sql, processar):
    email_id = inserir_email(sql, DESTINATARIO)
    provedor = ProvedorMemoria(falhas=[RuntimeError("bug no provedor")])

    resumo = processar(provedor)

    assert resumo.reagendados == 1
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "PENDENTE"
    assert linha["ultimo_erro"] == "RuntimeError: bug no provedor"


def test_falha_de_um_email_nao_impede_os_demais_do_lote(sql, processar):
    primeiro = inserir_email(sql, DESTINATARIO, criado_em_segundos=-30, assunto="primeiro")
    segundo = inserir_email(sql, DESTINATARIO, criado_em_segundos=-20, assunto="segundo")
    provedor = ProvedorMemoria(falhas=[ErroEnvioPermanente("recusado")])

    resumo = processar(provedor)

    assert (resumo.enviados, resumo.falhas) == (1, 1)
    assert linha_do_email(sql, primeiro)["status"] == "FALHA"
    assert linha_do_email(sql, segundo)["status"] == "ENVIADO"
    assert [m.assunto for m in provedor.enviadas] == ["segundo"]


# --- Quais e-mails o worker pega ---


def test_so_pega_pendentes_com_a_hora_vencida(sql, processar):
    vencido = inserir_email(sql, DESTINATARIO, proxima_em_segundos=-5, assunto="vencido")
    futuro = inserir_email(sql, DESTINATARIO, proxima_em_segundos=600, assunto="futuro")
    enviado = inserir_email(sql, DESTINATARIO, status="ENVIADO", com_corpo=False, tentativas=1)
    falha = inserir_email(sql, DESTINATARIO, status="FALHA", tentativas=5)
    provedor = ProvedorMemoria()

    resumo = processar(provedor)

    assert resumo.enviados == 1
    assert [m.assunto for m in provedor.enviadas] == ["vencido"]
    assert linha_do_email(sql, vencido)["status"] == "ENVIADO"
    assert linha_do_email(sql, futuro)["status"] == "PENDENTE"
    assert linha_do_email(sql, enviado)["tentativas"] == 1
    assert linha_do_email(sql, falha)["status"] == "FALHA"


def test_lote_respeita_o_limite_e_comeca_pelos_mais_antigos(sql, processar):
    for posicao, assunto in enumerate(["a", "b", "c"]):
        inserir_email(sql, DESTINATARIO, criado_em_segundos=-100 + posicao, assunto=assunto)
    provedor = ProvedorMemoria()

    primeiro = processar(provedor, lote=2)
    segundo = processar(provedor, lote=2)

    assert primeiro.total == 2 and segundo.total == 1
    assert [m.assunto for m in provedor.enviadas] == ["a", "b", "c"]


def test_reserva_respeita_limite_com_plano_nested_loop(sql, fila_vazia):
    sql("ANALYZE emails_outbox")
    ids = [inserir_email(sql, DESTINATARIO, assunto=f"plano-{n}") for n in range(3)]

    async def reservar(db):
        # O limite precisa valer também quando o otimizador escolhe nested loop,
        # sem depender da cardinalidade/estatísticas deixadas pelos testes anteriores.
        await db.exec(text("SET LOCAL enable_hashjoin = off"))
        await db.exec(text("SET LOCAL enable_mergejoin = off"))
        await db.exec(text("SET LOCAL enable_material = off"))
        await db.exec(text("SET LOCAL enable_indexscan = off"))
        await db.exec(text("SET LOCAL enable_bitmapscan = off"))
        await db.exec(text("SET LOCAL plan_cache_mode = force_generic_plan"))
        lote = await reservar_emails(db, limite=2, reserva_segundos=300)
        await db.commit()
        return lote

    primeiro = com_sessao(reservar)
    segundo = com_sessao(reservar)
    assert [item["id"] for item in primeiro] == ids[:2]
    assert [item["id"] for item in segundo] == ids[2:]
    assert all(linha_do_email(sql, id_)["tentativas"] == 1 for id_ in ids)


# --- Reserva: worker que caiu no meio do envio ---


def test_reserva_vencida_volta_para_a_fila_e_conta_outra_tentativa(sql, processar):
    email_id = inserir_email(
        sql, DESTINATARIO, status="ENVIANDO", tentativas=1, reservado_ate_em_segundos=-10
    )
    provedor = ProvedorMemoria()

    resumo = processar(provedor)

    assert resumo.enviados == 1
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "ENVIADO" and linha["tentativas"] == 2


def test_reserva_ainda_valida_nao_e_tocada(sql, processar):
    email_id = inserir_email(
        sql, DESTINATARIO, status="ENVIANDO", tentativas=1, reservado_ate_em_segundos=300
    )
    provedor = ProvedorMemoria()

    assert processar(provedor).total == 0
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "ENVIANDO" and linha["tentativas"] == 1


def test_reserva_vencida_sem_tentativas_restantes_vai_para_falha(sql, processar):
    email_id = inserir_email(
        sql,
        DESTINATARIO,
        status="ENVIANDO",
        tentativas=5,
        max_tentativas=5,
        reservado_ate_em_segundos=-10,
    )
    provedor = ProvedorMemoria()

    resumo = processar(provedor)

    assert resumo.total == 0 and provedor.tentativas == 0
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "FALHA" and linha["reservado_ate"] is None
    assert "tentativas acabaram" in linha["ultimo_erro"]


def test_o_envio_reserva_o_email_enquanto_o_provedor_trabalha(sql, processar):
    email_id = inserir_email(sql, DESTINATARIO)
    vistos = []

    def estado_por_fora() -> dict:
        return sql(
            "SELECT status::text AS status, tentativas, reservado_ate IS NOT NULL AS reservado"
            " FROM emails_outbox WHERE id = :id",
            id=email_id,
        )[0]

    class ProvedorQueConfereAReserva(ProvedorMemoria):
        async def enviar(self, mensagem):
            # Em outra thread, com outra conexão: é o que um observador externo veria
            vistos.append(await asyncio.to_thread(estado_por_fora))
            return await super().enviar(mensagem)

    processar(ProvedorQueConfereAReserva())

    assert vistos == [{"status": "ENVIANDO", "tentativas": 1, "reservado": True}]


# --- Concorrência ---


def test_workers_simultaneos_nunca_enviam_o_mesmo_email_duas_vezes(sql, processar):
    ids = [inserir_email(sql, DESTINATARIO, assunto=f"email-{n}") for n in range(6)]

    class ProvedorLento(ProvedorMemoria):
        async def enviar(self, mensagem):
            await asyncio.sleep(0.05)  # dá tempo de os outros workers reservarem a vez
            return await super().enviar(mensagem)

    provedor = ProvedorLento()

    resumos = processar(provedor, lote=2, simultaneos=3)

    assert sum(r.enviados for r in resumos) == 6
    assert sorted(m.assunto for m in provedor.enviadas) == [f"email-{n}" for n in range(6)]
    for id_ in ids:
        linha = linha_do_email(sql, id_)
        assert linha["status"] == "ENVIADO" and linha["tentativas"] == 1
