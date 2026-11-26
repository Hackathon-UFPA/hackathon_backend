-- BE-S5-06 (RF01, RF18, RF19, RF20, RF60): reenvio seguro e correção de convite pendente.
--
-- O convite passa a lembrar quantas vezes o aviso foi renovado e quando saiu o último, para a
-- API limitar o reenvio (intervalo mínimo e máximo por convite). `enviado_em` continua sendo o
-- momento da criação do convite, que ordena a listagem.
ALTER TABLE convites
    ADD COLUMN reenvios        smallint    NOT NULL DEFAULT 0,
    ADD COLUMN ultimo_envio_em timestamptz,
    ADD CONSTRAINT ck_convites_reenvios CHECK (reenvios >= 0);

-- `enviado_em` é `timestamp` em UTC: converte para um instante absoluto
UPDATE convites SET ultimo_envio_em = enviado_em AT TIME ZONE 'utc';

ALTER TABLE convites
    ALTER COLUMN ultimo_envio_em SET DEFAULT now(),
    ALTER COLUMN ultimo_envio_em SET NOT NULL;

COMMENT ON COLUMN convites.reenvios IS
    'Quantas vezes o aviso do convite foi renovado (reenvio ou troca de e-mail); a chave de idempotência do aviso usa este número';
COMMENT ON COLUMN convites.ultimo_envio_em IS
    'Instante (UTC) do último aviso: a criação do convite ou o último reenvio/troca de e-mail';
