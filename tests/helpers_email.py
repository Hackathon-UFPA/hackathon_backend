"""Apoio dos testes da fila de e-mails (BE-S5-05)."""


def inserir_email(
    sql,
    destinatario: str,
    *,
    tipo: str = "CONVITE_EQUIPE",
    status: str = "PENDENTE",
    tentativas: int = 0,
    max_tentativas: int = 5,
    proxima_em_segundos: int = 0,
    reservado_ate_em_segundos: int | None = None,
    criado_em_segundos: int = 0,
    chave: str | None = None,
    com_corpo: bool = True,
    assunto: str = "Assunto de teste",
) -> str:
    """Grava um e-mail direto na fila. Os tempos são relativos a agora (negativo = passado)."""
    enviado = "(now() AT TIME ZONE 'utc')" if status == "ENVIADO" else "NULL"
    reserva = (
        "NULL"
        if reservado_ate_em_segundos is None
        else "(now() AT TIME ZONE 'utc') + make_interval(secs => :reserva)"
    )
    params = dict(
        tipo=tipo,
        d=destinatario,
        assunto=assunto,
        texto="Texto do e-mail" if com_corpo else None,
        html="<p>Html do e-mail</p>" if com_corpo else None,
        chave=chave,
        status=status,
        tentativas=tentativas,
        max=max_tentativas,
        proxima=proxima_em_segundos,
        criado=criado_em_segundos,
    )
    if reservado_ate_em_segundos is not None:
        params["reserva"] = reservado_ate_em_segundos
    return sql(
        "INSERT INTO emails_outbox (tipo, destinatario_email, assunto, corpo_texto, corpo_html,"
        " chave_idempotencia, status, tentativas, max_tentativas, proxima_tentativa_em,"
        f" reservado_ate, enviado_em, criado_em) VALUES (CAST(:tipo AS tipo_email), :d, :assunto,"
        " :texto, :html, :chave, CAST(:status AS status_email), :tentativas, :max,"
        " (now() AT TIME ZONE 'utc') + make_interval(secs => :proxima),"
        f" {reserva}, {enviado},"
        " (now() AT TIME ZONE 'utc') + make_interval(secs => :criado)) RETURNING id",
        **params,
    )[0]["id"]


def linha_do_email(sql, email_id) -> dict:
    return sql(
        "SELECT *, EXTRACT(EPOCH FROM (proxima_tentativa_em - (now() AT TIME ZONE 'utc')))"
        " AS segundos_ate_a_proxima FROM emails_outbox WHERE id = :id",
        id=email_id,
    )[0]


def emails_de(sql, destinatario: str, tipo: str | None = None) -> list[dict]:
    """E-mails enfileirados para um endereço, do mais antigo ao mais novo."""
    return sql(
        "SELECT * FROM emails_outbox WHERE lower(destinatario_email) = lower(:d)"
        " AND (CAST(:t AS text) IS NULL OR tipo::text = :t) ORDER BY criado_em, id",
        d=destinatario,
        t=tipo,
    )
