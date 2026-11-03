-- BE-S4-06: rubrica de avaliação (RF16, RF17, RN09, RN10)
-- Uma rubrica por edição. Enquanto publicada_em é nulo, é um rascunho editável;
-- depois de publicada, nem a rubrica nem os critérios podem ser alterados (RN09).

CREATE TABLE rubricas (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id  uuid NOT NULL REFERENCES hackathon (id),
    publicada_em  timestamp,
    criado_em     timestamp DEFAULT (now() AT TIME ZONE 'utc'),
    atualizado_em timestamp,
    CONSTRAINT uq_rubricas_hackathon UNIQUE (hackathon_id)
);

COMMENT ON COLUMN rubricas.publicada_em IS 'Nulo enquanto rascunho; preenchido torna a rubrica imutável (RN09)';

CREATE TABLE criterios_rubrica (
    id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    rubrica_id uuid NOT NULL REFERENCES rubricas (id) ON DELETE CASCADE,
    nome       varchar NOT NULL,
    descricao  text NOT NULL,
    -- Percentual; a soma de 100% é conferida na publicação
    peso       numeric(5, 2) NOT NULL,
    escala_min smallint NOT NULL,
    escala_max smallint NOT NULL,
    ordem      smallint NOT NULL,
    CONSTRAINT uq_criterios_rubrica_nome UNIQUE (rubrica_id, nome),
    CONSTRAINT ck_criterios_rubrica_peso CHECK (peso > 0 AND peso <= 100),
    CONSTRAINT ck_criterios_rubrica_escala CHECK (escala_min >= 0 AND escala_min < escala_max)
);

CREATE INDEX idx_criterios_rubrica_rubrica_id ON criterios_rubrica (rubrica_id);

-- RN09 também fora da API. Excluir a rubrica inteira (com os critérios em cascata)
-- continua possível para remover uma edição; o que não se permite é alterá-la.
CREATE FUNCTION fn_rubrica_publicada_imutavel() RETURNS trigger AS $$
BEGIN
    IF OLD.publicada_em IS NOT NULL THEN
        RAISE EXCEPTION 'rubrica_publicada_imutavel: a rubrica % já foi publicada', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_rubricas_imutavel
    BEFORE UPDATE ON rubricas
    FOR EACH ROW EXECUTE FUNCTION fn_rubrica_publicada_imutavel();

CREATE FUNCTION fn_criterio_de_rubrica_publicada() RETURNS trigger AS $$
DECLARE
    alvo uuid;
BEGIN
    -- pg_trigger_depth() > 1: exclusão em cascata vinda do DELETE da rubrica
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'INSERT' THEN
        alvo := NEW.rubrica_id;
    ELSE
        alvo := OLD.rubrica_id;
    END IF;
    IF EXISTS (SELECT 1 FROM rubricas WHERE id = alvo AND publicada_em IS NOT NULL)
        OR (TG_OP = 'UPDATE' AND EXISTS (
            SELECT 1 FROM rubricas WHERE id = NEW.rubrica_id AND publicada_em IS NOT NULL))
    THEN
        RAISE EXCEPTION 'rubrica_publicada_imutavel: critérios de rubrica publicada não mudam'
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_criterios_rubrica_imutavel
    BEFORE INSERT OR UPDATE OR DELETE ON criterios_rubrica
    FOR EACH ROW EXECUTE FUNCTION fn_criterio_de_rubrica_publicada();
