-- BE-S6-01 e BE-S6-02: calendário comum da edição e registros das equipes.
CREATE TYPE tipo_marco_mentoria AS ENUM ('PARCIAL', 'FINAL');

CREATE TABLE marcos_mentoria (
    id uuid PRIMARY KEY,
    hackathon_id uuid NOT NULL REFERENCES hackathon(id),
    titulo varchar(255) NOT NULL CHECK (length(btrim(titulo)) > 0),
    descricao text NOT NULL CHECK (length(btrim(descricao)) BETWEEN 1 AND 20000),
    data_limite timestamptz NOT NULL,
    ordem integer NOT NULL DEFAULT 0 CHECK (ordem >= 0),
    tipo tipo_marco_mentoria NOT NULL DEFAULT 'PARCIAL',
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_marcos_mentoria_id_edicao UNIQUE (id, hackathon_id)
);

CREATE INDEX ix_marcos_mentoria_calendario
    ON marcos_mentoria (hackathon_id, data_limite, ordem, id);
CREATE UNIQUE INDEX uq_marcos_mentoria_final
    ON marcos_mentoria (hackathon_id) WHERE tipo = 'FINAL';

CREATE TABLE entregas_mentoria (
    id uuid PRIMARY KEY,
    marco_id uuid NOT NULL,
    equipe_id uuid NOT NULL,
    hackathon_id uuid NOT NULL,
    enviado_por uuid NOT NULL REFERENCES usuarios(id),
    enviado_em timestamptz NOT NULL,
    data_limite_no_envio timestamptz NOT NULL,
    descricao text NOT NULL CHECK (length(btrim(descricao)) BETWEEN 1 AND 20000),
    referencias text[] NOT NULL DEFAULT '{}',
    CONSTRAINT fk_entregas_mentoria_marco_edicao FOREIGN KEY (marco_id, hackathon_id)
        REFERENCES marcos_mentoria(id, hackathon_id),
    CONSTRAINT fk_entregas_mentoria_equipe_edicao FOREIGN KEY (equipe_id, hackathon_id)
        REFERENCES equipes(id, hackathon_id),
    CONSTRAINT uq_entregas_mentoria_marco_equipe UNIQUE (marco_id, equipe_id),
    CONSTRAINT ck_entregas_mentoria_prazo CHECK (enviado_em <= data_limite_no_envio)
);

CREATE INDEX ix_entregas_mentoria_equipe_historico
    ON entregas_mentoria (equipe_id, enviado_em DESC, id);
