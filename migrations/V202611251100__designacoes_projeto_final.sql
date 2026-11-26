-- BE-S6-09 (RF47, RF48, RN11, RN13, Q07): designação dos projetos finais ao Comitê Técnico.
-- Fica separada de designacoes_avaliacao, que é da avaliação científica das propostas.

-- Sem valor padrão: fica NULL até o Organizador configurar, e distribuir sem isso é recusado.
ALTER TABLE hackathon
    ADD COLUMN avaliadores_por_projeto_final smallint;

ALTER TABLE hackathon
    ADD CONSTRAINT ck_hackathon_avaliadores_por_projeto_final
        CHECK (avaliadores_por_projeto_final BETWEEN 2 AND 3);

COMMENT ON COLUMN hackathon.avaliadores_por_projeto_final IS
    'Avaliadores do Comitê Técnico por projeto final (2 a 3, Q07). Mudar o valor não altera designações já feitas.';

-- Projeto final = proposta aprovada na homologação do resultado científico (RF31).
-- Linhas nunca são apagadas: a redistribuição marca removida_em/removida_por (auditoria).
CREATE TABLE designacoes_projeto_final (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    submissao_id  uuid      NOT NULL REFERENCES submissoes (id),
    equipe_id     uuid      NOT NULL REFERENCES equipes (id),
    hackathon_id  uuid      NOT NULL REFERENCES hackathon (id),
    avaliador_id  uuid      NOT NULL REFERENCES usuarios (id),
    atribuido_por uuid      REFERENCES usuarios (id),
    atribuido_em  timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    removida_em   timestamp,
    removida_por  uuid      REFERENCES usuarios (id),
    CONSTRAINT ck_designacoes_projeto_final_remocao
        CHECK ((removida_em IS NULL) = (removida_por IS NULL))
);

-- Um avaliador só pode estar designado uma vez (vigente) ao mesmo projeto.
CREATE UNIQUE INDEX uq_designacoes_projeto_final_vigente
    ON designacoes_projeto_final (submissao_id, avaliador_id)
    WHERE removida_em IS NULL;

CREATE INDEX idx_designacoes_projeto_final_hackathon_id ON designacoes_projeto_final (hackathon_id);
CREATE INDEX idx_designacoes_projeto_final_avaliador_id ON designacoes_projeto_final (avaliador_id);

-- Conflitos de interesse declarados (RN13): o avaliador não pode avaliar o projeto da equipe.
-- Integrantes da equipe e mentores (atuais ou anteriores) já são bloqueados automaticamente.
CREATE TABLE conflitos_projeto_final (
    id             uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id   uuid      NOT NULL REFERENCES hackathon (id),
    equipe_id      uuid      NOT NULL REFERENCES equipes (id),
    avaliador_id   uuid      NOT NULL REFERENCES usuarios (id),
    motivo         text      NOT NULL CHECK (length(btrim(motivo)) > 0),
    registrado_por uuid      NOT NULL REFERENCES usuarios (id),
    registrado_em  timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_conflitos_projeto_final_equipe_avaliador UNIQUE (equipe_id, avaliador_id)
);

CREATE INDEX idx_conflitos_projeto_final_hackathon_id ON conflitos_projeto_final (hackathon_id);
