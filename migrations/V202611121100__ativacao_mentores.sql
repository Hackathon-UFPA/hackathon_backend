-- RN33: ativação própria do mentor, independente do comprovante de participantes.
ALTER TABLE usuarios
    ADD COLUMN mentor_perfil_concluido_em timestamp,
    ADD COLUMN mentor_ativado_em timestamp;

CREATE TABLE convites_mentor (
    id uuid PRIMARY KEY,
    usuario_id uuid NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    token_hash varchar(64) NOT NULL UNIQUE,
    criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    expira_em timestamp NOT NULL,
    utilizado_em timestamp,
    CONSTRAINT ck_convites_mentor_expiracao CHECK (expira_em > criado_em)
);
CREATE INDEX ix_convites_mentor_usuario ON convites_mentor(usuario_id);

COMMENT ON COLUMN usuarios.mentor_ativado_em IS
    'Conclusão inicial da RN33 pelo próprio mentor; não representa o ativo administrativo';
COMMENT ON TABLE convites_mentor IS
    'Token opaco de uso único para RN33; somente SHA-256 é persistido';
