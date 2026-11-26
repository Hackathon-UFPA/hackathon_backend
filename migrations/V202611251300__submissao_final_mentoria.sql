-- BE-S6-07: a entrega do marco FINAL é a identidade estável da submissão final.
ALTER TABLE marcos_mentoria
    ADD CONSTRAINT uq_marcos_mentoria_id_edicao_tipo UNIQUE (id, hackathon_id, tipo);

ALTER TABLE entregas_mentoria
    ADD CONSTRAINT uq_entregas_mentoria_vinculo UNIQUE (id, marco_id, equipe_id, hackathon_id);

CREATE TABLE submissoes_finais (
    entrega_id uuid PRIMARY KEY,
    marco_id uuid NOT NULL,
    equipe_id uuid NOT NULL,
    hackathon_id uuid NOT NULL,
    submissao_id uuid NOT NULL,
    tipo_marco tipo_marco_mentoria NOT NULL,
    repositorio_url varchar(2048) NOT NULL,
    repositorio_validado_em timestamptz NOT NULL,
    relatorio_pdf bytea NOT NULL,
    relatorio_tamanho_bytes integer GENERATED ALWAYS AS (octet_length(relatorio_pdf)) STORED
        NOT NULL,
    CONSTRAINT uq_submissoes_finais_proposta UNIQUE (submissao_id),
    CONSTRAINT ck_submissoes_finais_marco_final CHECK (tipo_marco = 'FINAL'),
    CONSTRAINT ck_submissoes_finais_tamanho CHECK (relatorio_tamanho_bytes BETWEEN 1 AND 10485760),
    CONSTRAINT fk_submissoes_finais_entrega
        FOREIGN KEY (entrega_id, marco_id, equipe_id, hackathon_id)
        REFERENCES entregas_mentoria (id, marco_id, equipe_id, hackathon_id),
    CONSTRAINT fk_submissoes_finais_marco_final
        FOREIGN KEY (marco_id, hackathon_id, tipo_marco)
        REFERENCES marcos_mentoria (id, hackathon_id, tipo),
    CONSTRAINT fk_submissoes_finais_proposta
        FOREIGN KEY (submissao_id, equipe_id, hackathon_id)
        REFERENCES submissoes (id, equipe_id, hackathon_id)
);

CREATE INDEX ix_submissoes_finais_equipe ON submissoes_finais (equipe_id);
