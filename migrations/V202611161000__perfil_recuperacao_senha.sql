-- BE-S5-07 (RF01, RF04, RF05, RF09; RN24): confirmação de e-mail, redefinição de senha por
-- token de uso único e revogação de sessões.
CREATE TYPE finalidade_token AS ENUM ('REDEFINICAO_SENHA', 'CONFIRMACAO_EMAIL');

ALTER TABLE usuarios
    ADD COLUMN email_confirmado_em timestamp,
    ADD COLUMN versao_sessao integer NOT NULL DEFAULT 0;

-- Quem ativou a conta por convite já provou a posse do e-mail (mentor, RN33).
UPDATE usuarios SET email_confirmado_em = mentor_ativado_em WHERE mentor_ativado_em IS NOT NULL;

COMMENT ON COLUMN usuarios.email_confirmado_em IS
    'Momento em que a posse do e-mail foi comprovada; NULL enquanto não confirmado. Informativo: não bloqueia o acesso';
COMMENT ON COLUMN usuarios.versao_sessao IS
    'Entra no token de acesso; aumentar o valor encerra todas as sessões abertas (troca ou redefinição de senha, logout)';

CREATE TABLE tokens_usuario (
    id uuid PRIMARY KEY,
    usuario_id uuid NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    finalidade finalidade_token NOT NULL,
    token_hash varchar(64) NOT NULL UNIQUE,
    -- Só na confirmação: o endereço que o token comprova (o atual ou um novo, em troca de e-mail)
    email varchar(255),
    criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    expira_em timestamp NOT NULL,
    utilizado_em timestamp,
    CONSTRAINT ck_tokens_usuario_expiracao CHECK (expira_em > criado_em),
    CONSTRAINT ck_tokens_usuario_email CHECK (
        (finalidade = 'CONFIRMACAO_EMAIL' AND email IS NOT NULL)
        OR (finalidade = 'REDEFINICAO_SENHA' AND email IS NULL)
    )
);
CREATE INDEX ix_tokens_usuario_usuario ON tokens_usuario(usuario_id, finalidade);

COMMENT ON TABLE tokens_usuario IS
    'Token opaco de uso único (redefinição de senha e confirmação de e-mail); somente o SHA-256 é persistido';
