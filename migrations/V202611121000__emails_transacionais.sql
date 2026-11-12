-- BE-S5-05 (RNF28, RF60): fila de e-mails transacionais (outbox).
--
-- O e-mail é gravado na mesma transação da ação que o originou (convite, inscrição, protocolo,
-- resultado...). Um worker envia depois, com tentativas automáticas. Assim, uma falha do
-- provedor nunca desfaz a ação principal e nenhum aviso se perde se a API cair.
--
-- O corpo (que pode ter links de acesso) é apagado assim que o provedor aceita a mensagem, e a
-- API administrativa nunca devolve o corpo.

CREATE TYPE tipo_email AS ENUM (
    'CONFIRMACAO_EMAIL', 'RECUPERACAO_SENHA', 'DEFINICAO_SENHA', 'CONVITE_EQUIPE',
    'INSCRICAO_CONCLUIDA', 'EQUIPE_HOMOLOGADA', 'PROTOCOLO_PROPOSTA', 'RESULTADO_PROPOSTA'
);
CREATE TYPE status_email AS ENUM ('PENDENTE', 'ENVIANDO', 'ENVIADO', 'FALHA');

CREATE TABLE emails_outbox (
    id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tipo                 tipo_email NOT NULL,
    destinatario_email   text NOT NULL,
    destinatario_nome    text,
    usuario_id           uuid REFERENCES usuarios (id) ON DELETE SET NULL,
    assunto              text NOT NULL,
    corpo_texto          text,
    corpo_html           text,
    -- Evita duplicar o mesmo aviso (ex.: um convite) se a ação for repetida
    chave_idempotencia   text,
    status               status_email NOT NULL DEFAULT 'PENDENTE',
    tentativas           smallint NOT NULL DEFAULT 0,
    max_tentativas       smallint NOT NULL,
    proxima_tentativa_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    reservado_ate        timestamp,
    ultimo_erro          text,
    provedor_mensagem_id text,
    enviado_em           timestamp,
    criado_em            timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    atualizado_em        timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_emails_outbox_chave UNIQUE (chave_idempotencia),
    CONSTRAINT ck_emails_outbox_tentativas CHECK (tentativas >= 0 AND max_tentativas >= 1),
    CONSTRAINT ck_emails_outbox_destinatario CHECK (
        destinatario_email !~ '[[:cntrl:]]' AND position('@' IN destinatario_email) > 1
    ),
    CONSTRAINT ck_emails_outbox_assunto CHECK (assunto !~ '[[:cntrl:]]'),
    CONSTRAINT ck_emails_outbox_enviado_em CHECK (status <> 'ENVIADO' OR enviado_em IS NOT NULL),
    -- Enquanto o e-mail ainda pode ser enviado, o corpo tem de existir
    CONSTRAINT ck_emails_outbox_corpo CHECK (
        status = 'ENVIADO' OR (corpo_texto IS NOT NULL AND corpo_html IS NOT NULL)
    ),
    CONSTRAINT ck_emails_outbox_reserva CHECK (status = 'ENVIANDO' OR reservado_ate IS NULL)
);

CREATE INDEX idx_emails_outbox_fila ON emails_outbox (status, proxima_tentativa_em);
CREATE INDEX idx_emails_outbox_usuario_id ON emails_outbox (usuario_id);
CREATE INDEX idx_emails_outbox_destinatario ON emails_outbox (lower(destinatario_email));

COMMENT ON TABLE emails_outbox IS
    'RNF28: fila de e-mails transacionais, gravada na transação da ação de origem.';
COMMENT ON COLUMN emails_outbox.corpo_texto IS 'Apagado depois do envio (pode conter links de acesso)';
COMMENT ON COLUMN emails_outbox.reservado_ate IS 'Reserva do worker; vencida, o e-mail volta para a fila';
COMMENT ON COLUMN emails_outbox.chave_idempotencia IS 'Mesma chave, mesmo aviso: a segunda gravação é ignorada';
