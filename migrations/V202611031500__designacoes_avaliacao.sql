-- BE-S4-09 (RF29, Q07): quantas pessoas avaliam cada proposta e quem foi designado a quem.

-- Sem valor padrão: fica NULL até o Organizador configurar, e distribuir sem isso é recusado.
ALTER TABLE hackathon
    ADD COLUMN avaliadores_por_proposta smallint;

ALTER TABLE hackathon
    ADD CONSTRAINT ck_hackathon_avaliadores_por_proposta
        CHECK (avaliadores_por_proposta BETWEEN 2 AND 3);

COMMENT ON COLUMN hackathon.avaliadores_por_proposta IS
    'Avaliadores por proposta (2 a 3, Q07). Mudar o valor não altera designações já feitas.';

-- Designação: o vínculo entre uma proposta e um avaliador (Comitê Científico).
-- A nota fica em avaliacoes; esta tabela diz apenas quem pode avaliar o quê.
CREATE TABLE designacoes_avaliacao (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    submissao_id uuid      NOT NULL REFERENCES submissoes (id),
    hackathon_id uuid      NOT NULL REFERENCES hackathon (id),
    avaliador_id uuid      NOT NULL REFERENCES usuarios (id),
    atribuido_por uuid     REFERENCES usuarios (id),
    atribuido_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_designacoes_submissao_avaliador UNIQUE (submissao_id, avaliador_id)
);

CREATE INDEX idx_designacoes_avaliacao_hackathon_id ON designacoes_avaliacao (hackathon_id);
CREATE INDEX idx_designacoes_avaliacao_avaliador_id ON designacoes_avaliacao (avaliador_id);
