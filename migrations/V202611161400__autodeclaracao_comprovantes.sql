-- BE-S5-03 (RF01, RF18, RF20 a RF23; RN01, RN05, RN25): autodeclaração de vínculo e comprovantes
-- individuais por tipo de integrante.
--
-- Autodeclaração é o que a própria pessoa afirma sobre o seu vínculo (estudante ou profissional);
-- comprovação aprovada é o que o conferente verificou em um documento. As duas ficam separadas:
-- a declaração vive em `autodeclaracoes_vinculo`, que só recebe linhas novas (cada alteração é uma
-- linha, com data), e a comprovação continua em `comprovantes_vinculo`, agora com o tipo de
-- vínculo que o documento comprova e a declaração que ele sustenta.
CREATE TABLE autodeclaracoes_vinculo (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    usuario_id   uuid      NOT NULL REFERENCES usuarios (id),
    hackathon_id uuid      NOT NULL REFERENCES hackathon (id),
    tipo         tipo_integrante NOT NULL,
    -- Estudante: instituição, curso e período
    instituicao  text,
    curso        text,
    periodo      smallint,
    -- Profissional: organização e cargo
    organizacao  text,
    cargo        text,
    declarada_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT ck_autodeclaracoes_estudante CHECK (
        tipo <> 'ESTUDANTE'
        OR (instituicao IS NOT NULL AND curso IS NOT NULL AND periodo IS NOT NULL AND periodo > 0
            AND organizacao IS NULL AND cargo IS NULL)
    ),
    CONSTRAINT ck_autodeclaracoes_profissional CHECK (
        tipo <> 'PROFISSIONAL'
        OR (organizacao IS NOT NULL AND cargo IS NOT NULL
            AND instituicao IS NULL AND curso IS NULL AND periodo IS NULL)
    )
);

CREATE INDEX idx_autodeclaracoes_usuario_edicao
    ON autodeclaracoes_vinculo (usuario_id, hackathon_id, declarada_em DESC, id);
CREATE INDEX idx_autodeclaracoes_hackathon_id ON autodeclaracoes_vinculo (hackathon_id);

-- Auditoria: uma declaração gravada não é alterada, nem pela API nem por fora dela. A pessoa
-- corrige declarando de novo. Excluir continua possível (remoção de uma edição ou de um usuário).
CREATE FUNCTION fn_autodeclaracao_imutavel() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'autodeclaracao_imutavel: a autodeclaração gravada não pode ser alterada'
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_autodeclaracoes_vinculo_imutavel
    BEFORE UPDATE ON autodeclaracoes_vinculo
    FOR EACH ROW EXECUTE FUNCTION fn_autodeclaracao_imutavel();

COMMENT ON TABLE autodeclaracoes_vinculo IS
    'Autodeclaração de vínculo da própria pessoa por edição (só inserção). Não prova nada: a comprovação é o comprovante aprovado.';

-- O comprovante passa a dizer qual vínculo comprova. Os que já existem eram acadêmicos.
ALTER TABLE comprovantes_vinculo
    ADD COLUMN tipo_vinculo tipo_integrante NOT NULL DEFAULT 'ESTUDANTE',
    ADD COLUMN autodeclaracao_id uuid REFERENCES autodeclaracoes_vinculo (id) ON DELETE SET NULL;

CREATE INDEX idx_comprovantes_vinculo_autodeclaracao_id ON comprovantes_vinculo (autodeclaracao_id);

-- Quem muda de tipo precisa de um comprovante do tipo novo, mesmo já tendo um aprovado do outro:
-- o limite de um comprovante em aberto ou aprovado passa a valer por tipo.
DROP INDEX uq_comprovantes_vinculo_ativo;
CREATE UNIQUE INDEX uq_comprovantes_vinculo_ativo
    ON comprovantes_vinculo (usuario_id, hackathon_id, tipo_vinculo)
    WHERE status <> 'RECUSADO';

COMMENT ON COLUMN comprovantes_vinculo.tipo_vinculo IS 'Vínculo que o documento comprova; legado = ESTUDANTE';
COMMENT ON COLUMN comprovantes_vinculo.autodeclaracao_id IS 'Declaração que o comprovante sustenta, quando houver';

-- Política de verificação por edição, provisória até o Squad 1 validar a elegibilidade.
-- exige_autodeclaracao nasce falso para não criar uma exigência nova em edições já em andamento.
ALTER TABLE hackathon
    ADD COLUMN exige_autodeclaracao           boolean NOT NULL DEFAULT false,
    ADD COLUMN exige_comprovante_estudante    boolean NOT NULL DEFAULT true,
    ADD COLUMN exige_comprovante_profissional boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN hackathon.exige_autodeclaracao IS 'Homologação exige a autodeclaração de cada integrante (política provisória)';
COMMENT ON COLUMN hackathon.exige_comprovante_estudante IS 'Homologação exige comprovante aprovado de quem é ESTUDANTE (política provisória)';
COMMENT ON COLUMN hackathon.exige_comprovante_profissional IS 'Homologação exige comprovante aprovado de quem é PROFISSIONAL (política provisória)';
