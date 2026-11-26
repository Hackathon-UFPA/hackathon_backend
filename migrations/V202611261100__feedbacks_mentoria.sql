-- BE-S6-03 (RF40, RF42, RN16, RN17): feedbacks do mentor às equipes, imutáveis.
-- Corrigir um feedback é criar outro com corrige_id. O original nunca muda.
-- Os valores de status_acompanhamento são provisórios (o grupo ainda valida a lista): varchar com
-- CHECK, para trocar a lista sem migrar um tipo enum.
CREATE TABLE feedbacks_mentoria (
    id uuid PRIMARY KEY,
    equipe_id uuid NOT NULL,
    hackathon_id uuid NOT NULL,
    -- Vínculo do mentor que escreveu. Não é exposto pela API.
    atribuicao_id uuid NOT NULL REFERENCES atribuicoes_mentor(id),
    autor_id uuid NOT NULL REFERENCES usuarios(id),
    marco_id uuid,
    entrega_id uuid,
    status_acompanhamento varchar(20) NOT NULL,
    texto text NOT NULL,
    corrige_id uuid,
    criado_em timestamptz NOT NULL DEFAULT now(),
    chave_idempotencia varchar(128),
    CONSTRAINT fk_feedbacks_mentoria_equipe_edicao FOREIGN KEY (equipe_id, hackathon_id)
        REFERENCES equipes(id, hackathon_id),
    CONSTRAINT fk_feedbacks_mentoria_marco_edicao FOREIGN KEY (marco_id, hackathon_id)
        REFERENCES marcos_mentoria(id, hackathon_id),
    -- Reaproveita a unicidade da entrega: com entrega informada, marco e equipe batem com ela.
    CONSTRAINT fk_feedbacks_mentoria_entrega FOREIGN KEY (entrega_id, marco_id, equipe_id, hackathon_id)
        REFERENCES entregas_mentoria(id, marco_id, equipe_id, hackathon_id),
    CONSTRAINT uq_feedbacks_mentoria_original UNIQUE (id, equipe_id, autor_id),
    -- A correção é da mesma equipe e do mesmo autor do feedback corrigido.
    CONSTRAINT fk_feedbacks_mentoria_corrige FOREIGN KEY (corrige_id, equipe_id, autor_id)
        REFERENCES feedbacks_mentoria(id, equipe_id, autor_id),
    CONSTRAINT uq_feedbacks_mentoria_autor_chave UNIQUE (autor_id, chave_idempotencia),
    CONSTRAINT ck_feedbacks_mentoria_status CHECK (
        status_acompanhamento IN ('NO_RITMO', 'ATENCAO', 'EM_RISCO', 'CONCLUIDO')
    ),
    CONSTRAINT ck_feedbacks_mentoria_texto CHECK (length(btrim(texto)) BETWEEN 1 AND 5000),
    -- Com a FK composta (MATCH SIMPLE), entrega sem marco escaparia da verificação.
    CONSTRAINT ck_feedbacks_mentoria_entrega_marco CHECK (entrega_id IS NULL OR marco_id IS NOT NULL),
    CONSTRAINT ck_feedbacks_mentoria_corrige CHECK (corrige_id IS NULL OR corrige_id <> id),
    CONSTRAINT ck_feedbacks_mentoria_chave CHECK (
        chave_idempotencia IS NULL OR length(chave_idempotencia) BETWEEN 1 AND 128
    )
);

CREATE INDEX ix_feedbacks_mentoria_equipe ON feedbacks_mentoria (equipe_id, criado_em DESC, id);
CREATE INDEX ix_feedbacks_mentoria_entrega ON feedbacks_mentoria (entrega_id)
    WHERE entrega_id IS NOT NULL;
CREATE INDEX ix_feedbacks_mentoria_marco ON feedbacks_mentoria (marco_id)
    WHERE marco_id IS NOT NULL;
-- Cada feedback é corrigido no máximo uma vez, inclusive com pedidos simultâneos.
CREATE UNIQUE INDEX uq_feedbacks_mentoria_corrige ON feedbacks_mentoria (corrige_id)
    WHERE corrige_id IS NOT NULL;

-- Append-only: a API não tem UPDATE nem DELETE, e o banco recusa os dois. As chaves estrangeiras
-- para equipes, usuários e atribuições não têm ON DELETE CASCADE: apagar quem tem feedback falha.
CREATE FUNCTION bloquear_alteracao_feedback_mentoria() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'feedbacks_mentoria é imutável: % não é permitido', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_feedbacks_mentoria_imutavel
    BEFORE UPDATE OR DELETE ON feedbacks_mentoria
    FOR EACH ROW EXECUTE FUNCTION bloquear_alteracao_feedback_mentoria();

COMMENT ON TABLE feedbacks_mentoria IS 'Feedbacks do mentor (append-only); correção = novo registro com corrige_id';
COMMENT ON COLUMN feedbacks_mentoria.atribuicao_id IS 'Vínculo vigente do mentor no momento da escrita; não exposto na API';
