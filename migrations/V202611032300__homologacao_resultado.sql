-- BE-S4-11 (RF31, RF32): homologação do resultado da avaliação científica e divulgação
-- das propostas aprovadas.
--
-- A homologação é única por hackathon e grava um retrato do resultado no momento em que
-- foi feita (notas, classificação e aprovação de cada proposta). Esse retrato é o que a
-- consulta pública lê, então nada que mude depois (nome da equipe, novas avaliações) altera
-- o resultado oficial. Fica registrado quem homologou e quando.

CREATE TABLE homologacoes_resultado (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id    uuid      NOT NULL REFERENCES hackathon (id),
    homologado_por  uuid      NOT NULL REFERENCES usuarios (id),
    homologado_em   timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    total_propostas integer   NOT NULL CHECK (total_propostas >= 0),
    total_aprovadas integer   NOT NULL CHECK (total_aprovadas >= 0),
    CONSTRAINT uq_homologacoes_resultado_hackathon UNIQUE (hackathon_id),
    CONSTRAINT ck_homologacoes_resultado_aprovadas CHECK (total_aprovadas <= total_propostas)
);

CREATE TABLE resultados_proposta (
    id                       uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    homologacao_id           uuid     NOT NULL REFERENCES homologacoes_resultado (id) ON DELETE CASCADE,
    hackathon_id             uuid     NOT NULL REFERENCES hackathon (id),
    submissao_id             uuid     NOT NULL REFERENCES submissoes (id),
    equipe_id                uuid     NOT NULL REFERENCES equipes (id),
    -- Cópia dos textos divulgados: o resultado não muda se a equipe for renomeada depois.
    equipe_nome              text,
    tema_titulo              text,
    titulo                   text,
    nota_media               numeric(5, 2) NOT NULL,
    classificacao            integer  NOT NULL CHECK (classificacao >= 1),
    avaliacoes               smallint NOT NULL CHECK (avaliacoes >= 1),
    recomendacoes_aprovacao  smallint NOT NULL CHECK (recomendacoes_aprovacao >= 0),
    recomendacoes_reprovacao smallint NOT NULL CHECK (recomendacoes_reprovacao >= 0),
    aprovada                 boolean  NOT NULL,
    CONSTRAINT uq_resultados_proposta_submissao UNIQUE (submissao_id),
    CONSTRAINT uq_resultados_proposta_classificacao UNIQUE (homologacao_id, classificacao)
);

CREATE INDEX idx_resultados_proposta_hackathon_id ON resultados_proposta (hackathon_id);

-- RF31: depois de homologado, o resultado fica bloqueado também fora da API.
-- Excluir continua possível (remoção de uma edição inteira); alterar, não.
CREATE FUNCTION fn_resultado_homologado_imutavel() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'resultado_homologado_imutavel: o resultado homologado não pode ser alterado'
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_homologacoes_resultado_imutavel
    BEFORE UPDATE ON homologacoes_resultado
    FOR EACH ROW EXECUTE FUNCTION fn_resultado_homologado_imutavel();

CREATE TRIGGER tg_resultados_proposta_imutavel
    BEFORE UPDATE ON resultados_proposta
    FOR EACH ROW EXECUTE FUNCTION fn_resultado_homologado_imutavel();

COMMENT ON TABLE homologacoes_resultado IS
    'RF31: homologação única do resultado da avaliação científica por hackathon (auditoria: quem e quando).';
COMMENT ON TABLE resultados_proposta IS
    'RF31/RF32: retrato imutável do resultado de cada proposta no momento da homologação.';
COMMENT ON COLUMN resultados_proposta.aprovada IS
    'Decisão do Organizador na homologação (critério definitivo de aprovação ainda pendente).';
