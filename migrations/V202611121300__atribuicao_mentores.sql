-- RF38/RN16/RN24/RN33: mentoria por equipe, com histórico e notificações duráveis.
ALTER TYPE tipo_email ADD VALUE 'ATRIBUICAO_MENTOR';
ALTER TABLE hackathon
    ADD COLUMN treinamento_concluido_em timestamp,
    ADD COLUMN treinamento_concluido_por uuid REFERENCES usuarios(id),
    ADD CONSTRAINT ck_hackathon_treinamento CHECK (
        (treinamento_concluido_em IS NULL) = (treinamento_concluido_por IS NULL)
    );

CREATE TABLE atribuicoes_mentor (
    id uuid PRIMARY KEY,
    equipe_id uuid NOT NULL,
    hackathon_id uuid NOT NULL REFERENCES hackathon(id),
    mentor_id uuid NOT NULL REFERENCES usuarios(id),
    atribuido_por uuid NOT NULL REFERENCES usuarios(id),
    atribuido_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    atribuicao_anterior_id uuid,
    motivo text,
    encerrada_em timestamp,
    encerrada_por uuid REFERENCES usuarios(id),
    motivo_encerramento text,
    CONSTRAINT fk_atribuicoes_equipe_edicao FOREIGN KEY (equipe_id, hackathon_id)
        REFERENCES equipes(id, hackathon_id),
    CONSTRAINT uq_atribuicoes_id_equipe UNIQUE (id, equipe_id),
    CONSTRAINT uq_atribuicoes_sucessora UNIQUE (atribuicao_anterior_id),
    CONSTRAINT fk_atribuicoes_anterior FOREIGN KEY (atribuicao_anterior_id, equipe_id)
        REFERENCES atribuicoes_mentor(id, equipe_id),
    CONSTRAINT ck_atribuicoes_anterior CHECK (atribuicao_anterior_id IS DISTINCT FROM id),
    CONSTRAINT ck_atribuicoes_encerramento CHECK (
        (encerrada_em IS NULL AND encerrada_por IS NULL AND motivo_encerramento IS NULL)
        OR (encerrada_em IS NOT NULL AND encerrada_em >= atribuido_em AND encerrada_por IS NOT NULL
            AND motivo_encerramento IS NOT NULL
            AND length(trim(motivo_encerramento)) > 0)
    )
);
CREATE UNIQUE INDEX uq_atribuicoes_mentor_equipe_vigente ON atribuicoes_mentor(equipe_id)
    WHERE encerrada_em IS NULL;
CREATE INDEX ix_atribuicoes_mentor_vigentes ON atribuicoes_mentor(mentor_id)
    WHERE encerrada_em IS NULL;
CREATE INDEX ix_atribuicoes_mentor_edicao ON atribuicoes_mentor(hackathon_id, equipe_id);

-- Ponto de integração da futura central in-app, sem criar outra central neste card.
CREATE TABLE eventos_notificacao_mentoria (
    id uuid PRIMARY KEY,
    atribuicao_id uuid NOT NULL REFERENCES atribuicoes_mentor(id),
    usuario_id uuid NOT NULL REFERENCES usuarios(id),
    tipo text NOT NULL CHECK (tipo IN ('ATRIBUIDA', 'SUBSTITUIDA', 'ENCERRADA')),
    mensagem text NOT NULL,
    criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    email_enfileirado boolean NOT NULL DEFAULT false,
    publicado_na_plataforma_em timestamp,
    CONSTRAINT uq_eventos_mentoria_destinatario UNIQUE (atribuicao_id, tipo, usuario_id)
);
CREATE INDEX ix_eventos_mentoria_pendentes ON eventos_notificacao_mentoria(criado_em, id)
    WHERE publicado_na_plataforma_em IS NULL;
COMMENT ON TABLE atribuicoes_mentor IS
    'Vínculo auditável mentor/equipe; id estável pode identificar a conversa futura. Encerramento lógico.';
COMMENT ON TABLE eventos_notificacao_mentoria IS
    'RF60: eventos por destinatário para a central in-app; NULL publicado_na_plataforma_em indica consumo pendente.';
