-- BE-S5-02 (RF01, RF18, RF19, RF22, RF23; RN01 a RN06): cadastrar equipe e integrantes em um fluxo.
--
-- 1) Convite com cadastro próprio: quem ainda não tem conta recebe, no e-mail do convite, um link de
--    uso único para criar o próprio acesso, sem que o líder jamais defina senha. Como nos convites de
--    mentor e nos links de redefinição, o banco guarda só o SHA-256 do token; o valor puro existe
--    apenas no e-mail enviado.
-- 2) POST /equipes idempotente: a chave enviada pelo líder (Idempotency-Key) e um hash do conteúdo
--    ficam na equipe, para um retry devolver a equipe já criada em vez de duplicar ou dar erro.
ALTER TABLE convites
    ADD COLUMN token_hash          varchar(64),
    ADD COLUMN token_expira_em     timestamp,
    ADD COLUMN token_utilizado_em  timestamp,
    ADD CONSTRAINT ck_convites_token CHECK (token_hash IS NULL OR token_expira_em IS NOT NULL);

CREATE UNIQUE INDEX uq_convites_token_hash ON convites (token_hash) WHERE token_hash IS NOT NULL;

COMMENT ON COLUMN convites.token_hash IS
    'SHA-256 do token do link de cadastro próprio (só para e-mail sem conta); o token puro só existe no e-mail';
COMMENT ON COLUMN convites.token_utilizado_em IS
    'Quando o link de cadastro foi usado; o convite segue PENDENTE até a pessoa aceitar ou recusar';

ALTER TABLE equipes
    ADD COLUMN criada_por         uuid REFERENCES usuarios (id) ON DELETE SET NULL,
    ADD COLUMN chave_idempotencia varchar(128),
    ADD COLUMN hash_requisicao    varchar(64),
    ADD CONSTRAINT ck_equipes_idempotencia
        CHECK ((chave_idempotencia IS NULL) = (hash_requisicao IS NULL));

CREATE UNIQUE INDEX uq_equipes_idempotencia ON equipes (criada_por, chave_idempotencia)
    WHERE chave_idempotencia IS NOT NULL;

COMMENT ON COLUMN equipes.criada_por IS 'Quem criou a equipe (o líder inicial); vazio nas equipes anteriores à BE-S5-02';
COMMENT ON COLUMN equipes.chave_idempotencia IS 'Idempotency-Key do POST /equipes, única por quem criou';
COMMENT ON COLUMN equipes.hash_requisicao IS 'SHA-256 do conteúdo do POST /equipes que usou a chave';
