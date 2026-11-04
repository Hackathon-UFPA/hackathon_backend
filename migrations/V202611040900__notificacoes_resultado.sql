-- BE-S4-12 (RF33, RF34): notificação do resultado aos integrantes da equipe.
--
-- Uma linha por integrante e por canal, criada na mesma transação da homologação do resultado.
-- O canal definitivo (plataforma, e-mail ou ambos) depende da decisão Q16, ainda em aberto:
-- por ora só PLATAFORMA é usado e o valor EMAIL fica reservado para quando a infraestrutura
-- de e-mail existir. `status_envio` torna o envio rastreável (PENDENTE, ENVIADO, FALHA).
-- A notificação na plataforma nasce ENVIADO: ela já está visível ao integrante.

CREATE TYPE canal_notificacao AS ENUM ('PLATAFORMA', 'EMAIL');
CREATE TYPE status_envio_notificacao AS ENUM ('PENDENTE', 'ENVIADO', 'FALHA');

CREATE TABLE notificacoes_resultado (
    id             uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    homologacao_id uuid NOT NULL REFERENCES homologacoes_resultado (id) ON DELETE CASCADE,
    hackathon_id   uuid NOT NULL REFERENCES hackathon (id),
    equipe_id      uuid NOT NULL REFERENCES equipes (id),
    submissao_id   uuid NOT NULL REFERENCES submissoes (id),
    usuario_id     uuid NOT NULL REFERENCES usuarios (id),
    aprovada       boolean NOT NULL,
    mensagem       text NOT NULL,
    canal          canal_notificacao NOT NULL,
    status_envio   status_envio_notificacao NOT NULL,
    enviado_em     timestamp,
    erro           text,
    criado_em      timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_notificacoes_resultado_destinatario UNIQUE (homologacao_id, usuario_id, canal),
    CONSTRAINT ck_notificacoes_resultado_enviado_em
        CHECK (status_envio <> 'ENVIADO' OR enviado_em IS NOT NULL),
    CONSTRAINT ck_notificacoes_resultado_erro
        CHECK (erro IS NULL OR status_envio = 'FALHA')
);

CREATE INDEX idx_notificacoes_resultado_usuario_id ON notificacoes_resultado (usuario_id);
CREATE INDEX idx_notificacoes_resultado_status ON notificacoes_resultado (status_envio);

COMMENT ON TABLE notificacoes_resultado IS
    'RF33: aviso do resultado a cada integrante, com canal e status de envio rastreáveis.';
