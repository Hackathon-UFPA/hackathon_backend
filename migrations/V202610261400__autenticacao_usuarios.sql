-- Autenticação (RF01, RF02, RF06): senha, bloqueio por tentativas e situação da conta.
-- A regra de bloqueio (quantas falhas, por quanto tempo) fica no service; o banco só guarda o estado.

CREATE TYPE situacao_conta AS ENUM ('PENDENTE', 'ATIVA');

ALTER TABLE usuarios
    ADD COLUMN senha_hash       varchar,
    ADD COLUMN tentativas_login smallint NOT NULL DEFAULT 0
        CONSTRAINT ck_usuarios_tentativas_login CHECK (tentativas_login >= 0),
    ADD COLUMN bloqueado_ate    timestamp,
    ADD COLUMN situacao_conta   situacao_conta NOT NULL DEFAULT 'ATIVA';

COMMENT ON COLUMN usuarios.senha_hash IS 'Argon2; NULL em contas sem login por senha';
COMMENT ON COLUMN usuarios.bloqueado_ate IS 'UTC. Login recusado enquanto for maior que agora';
COMMENT ON COLUMN usuarios.situacao_conta IS
    'PENDENTE até o Comitê Científico aprovar o comprovante de vínculo (RN25)';

-- E-mail único sem diferenciar maiúsculas (o UNIQUE original diferencia)
CREATE UNIQUE INDEX uq_usuarios_email_lower ON usuarios (lower(email));
