-- BE-S5-08 (RF16, RF17, RN09, RN10): duas rubricas por edição, uma por fase.
-- PROPOSTA avalia as propostas (avaliação científica); PROJETO_FINAL avalia os projetos
-- finais. Critérios e pesos são independentes entre as fases.
--
-- A rubrica que já existe vira a da fase PROPOSTA. O ADD COLUMN com DEFAULT não dispara
-- os gatilhos de UPDATE, então a rubrica publicada, os critérios e as avaliações feitas
-- com ela continuam exatamente como estavam (RN09).

CREATE TYPE fase_rubrica AS ENUM ('PROPOSTA', 'PROJETO_FINAL');

ALTER TABLE rubricas ADD COLUMN fase fase_rubrica NOT NULL DEFAULT 'PROPOSTA';

COMMENT ON COLUMN rubricas.fase IS 'PROPOSTA (avaliação científica) ou PROJETO_FINAL; uma rubrica por fase em cada edição';

ALTER TABLE rubricas DROP CONSTRAINT uq_rubricas_hackathon;
ALTER TABLE rubricas ADD CONSTRAINT uq_rubricas_hackathon_fase UNIQUE (hackathon_id, fase);

-- A avaliação científica só pode usar a rubrica da fase PROPOSTA.
CREATE FUNCTION fn_avaliacao_usa_rubrica_da_proposta() RETURNS trigger AS $$
BEGIN
    IF NEW.rubrica_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM rubricas WHERE id = NEW.rubrica_id AND fase <> 'PROPOSTA'
    ) THEN
        RAISE EXCEPTION 'avaliacao_rubrica_fase: a avaliação científica usa a rubrica da fase PROPOSTA'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_avaliacoes_rubrica_da_proposta
    BEFORE INSERT OR UPDATE OF rubrica_id ON avaliacoes
    FOR EACH ROW EXECUTE FUNCTION fn_avaliacao_usa_rubrica_da_proposta();
