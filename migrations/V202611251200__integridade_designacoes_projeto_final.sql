-- Correção complementar da BE-S6-09: validar também as designações já removidas.
DO $$
DECLARE
    id_inconsistente uuid;
BEGIN
    SELECT d.id INTO id_inconsistente
    FROM designacoes_projeto_final AS d
    WHERE NOT EXISTS (
        SELECT 1 FROM submissoes AS s
        WHERE (s.id, s.equipe_id, s.hackathon_id) = (d.submissao_id, d.equipe_id, d.hackathon_id)
    )
    ORDER BY d.id LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION 'Designação de projeto final % tem submissão, equipe ou edição incompatível',
            id_inconsistente USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT c.id INTO id_inconsistente
    FROM conflitos_projeto_final AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM equipes AS e
        WHERE (e.id, e.hackathon_id) = (c.equipe_id, c.hackathon_id)
    )
    ORDER BY c.id LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION 'Conflito de projeto final % tem equipe e edição incompatíveis',
            id_inconsistente USING ERRCODE = 'foreign_key_violation';
    END IF;
END;
$$;

ALTER TABLE submissoes
    ADD CONSTRAINT uq_submissoes_id_equipe_edicao UNIQUE (id, equipe_id, hackathon_id);

ALTER TABLE designacoes_projeto_final
    ADD CONSTRAINT fk_designacoes_projeto_final_submissao_equipe_edicao
        FOREIGN KEY (submissao_id, equipe_id, hackathon_id)
        REFERENCES submissoes (id, equipe_id, hackathon_id),
    DROP CONSTRAINT designacoes_projeto_final_submissao_id_fkey,
    DROP CONSTRAINT designacoes_projeto_final_equipe_id_fkey,
    DROP CONSTRAINT designacoes_projeto_final_hackathon_id_fkey;

ALTER TABLE conflitos_projeto_final
    ADD CONSTRAINT fk_conflitos_projeto_final_equipe_edicao
        FOREIGN KEY (equipe_id, hackathon_id) REFERENCES equipes (id, hackathon_id),
    DROP CONSTRAINT conflitos_projeto_final_equipe_id_fkey,
    DROP CONSTRAINT conflitos_projeto_final_hackathon_id_fkey;
