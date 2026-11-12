-- Convites anteriores não possuem edição confiável: preservar o histórico e revogá-los.
ALTER TABLE convites_mentor
    ADD COLUMN hackathon_id uuid REFERENCES hackathon(id),
    ADD COLUMN email_enfileirado boolean NOT NULL DEFAULT false;
UPDATE convites_mentor SET utilizado_em = COALESCE(utilizado_em, (now() AT TIME ZONE 'utc'));
ALTER TABLE convites_mentor ADD CONSTRAINT ck_convites_mentor_edicao CHECK (
    hackathon_id IS NOT NULL OR utilizado_em IS NOT NULL
);
UPDATE convites_mentor c SET email_enfileirado = true
WHERE EXISTS (SELECT 1 FROM emails_outbox e WHERE e.chave_idempotencia = 'convite-mentor:' || c.id::text);
CREATE INDEX ix_convites_mentor_edicao ON convites_mentor(usuario_id, hackathon_id);

ALTER TABLE emails_outbox ADD COLUMN cancelado_em timestamp;
ALTER TABLE emails_outbox DROP CONSTRAINT ck_emails_outbox_corpo;
ALTER TABLE emails_outbox ADD CONSTRAINT ck_emails_outbox_corpo CHECK (
    status = 'ENVIADO' OR cancelado_em IS NOT NULL
    OR (corpo_texto IS NOT NULL AND corpo_html IS NOT NULL)
);
ALTER TABLE emails_outbox ADD CONSTRAINT ck_emails_outbox_cancelado CHECK (
    cancelado_em IS NULL OR (status = 'FALHA' AND reservado_ate IS NULL)
);
-- Apenas convites antigos, nunca mensagens já enviadas ou e-mails de outros fluxos.
UPDATE emails_outbox SET status = 'FALHA', cancelado_em = (now() AT TIME ZONE 'utc'),
    reservado_ate = NULL, corpo_texto = NULL, corpo_html = NULL,
    ultimo_erro = 'Convite de mentor revogado; emita um novo convite com a edição.',
    atualizado_em = (now() AT TIME ZONE 'utc')
WHERE status <> 'ENVIADO' AND chave_idempotencia IN (
    SELECT 'convite-mentor:' || id::text FROM convites_mentor
);
