-- BE-S4-10 (RF30, RN11, RN12). Não descarta nem escolhe entre avaliações legadas.
-- Duplicatas preexistentes exigem conciliação explícita antes de aplicar a migration.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM avaliacoes GROUP BY submissao_id, avaliador_id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'avaliacoes_duplicadas: concilie submissao_id + avaliador_id antes de migrar';
    END IF;
END;
$$;

CREATE TYPE status_avaliacao AS ENUM ('RASCUNHO', 'ENVIADA');
CREATE TYPE recomendacao_avaliacao AS ENUM ('APROVACAO', 'REPROVACAO');

ALTER TABLE avaliacoes
    ADD COLUMN rubrica_id uuid REFERENCES rubricas (id),
    ADD COLUMN status status_avaliacao NOT NULL DEFAULT 'RASCUNHO',
    ADD COLUMN recomendacao recomendacao_avaliacao,
    ADD COLUMN atualizado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    ADD CONSTRAINT uq_avaliacoes_submissao_avaliador UNIQUE (submissao_id, avaliador_id);

-- Notas e datas antigas são preservadas. Não inventa rubrica, critérios ou recomendação.
UPDATE avaliacoes SET status = 'ENVIADA', atualizado_em = COALESCE(avaliado_em, atualizado_em)
WHERE nota IS NOT NULL OR avaliado_em IS NOT NULL;

CREATE TABLE notas_criterio_avaliacao (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    avaliacao_id uuid NOT NULL REFERENCES avaliacoes (id) ON DELETE CASCADE,
    criterio_id uuid NOT NULL REFERENCES criterios_rubrica (id),
    nota numeric NOT NULL,
    CONSTRAINT uq_notas_avaliacao_criterio UNIQUE (avaliacao_id, criterio_id)
);

COMMENT ON COLUMN avaliacoes.nota IS
    'Nota final calculada pelo backend; normalização provisória 0 a 10 (validar com Squad 1). Legados preservados.';
