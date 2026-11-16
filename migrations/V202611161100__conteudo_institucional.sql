-- BE-S5-12 (RF10 a RF14, RF35, RF59; RN07, RN09; RNF20, RNF23): conteúdo institucional da edição
-- (descrição, apoiadores, FAQ, cronograma), versões do regulamento e agenda do treinamento.
-- Todo conteúdo nasce não publicado: só o publicado aparece nas rotas públicas.

ALTER TABLE hackathon ADD COLUMN descricao text;

-- Regulamento/termo em rascunho pode ser editado e excluído; publicado, vira imutável (RF11, RN05).
-- Os termos já existentes foram publicados, então ficam com rascunho = false.
ALTER TABLE termos ADD COLUMN rascunho boolean NOT NULL DEFAULT false;
ALTER TABLE termos ADD CONSTRAINT ck_termos_rascunho_nao_vigente CHECK (NOT (rascunho AND vigente));

CREATE TABLE apoiadores (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id uuid NOT NULL REFERENCES hackathon(id),
    nome varchar(255) NOT NULL,
    categoria varchar(80) NOT NULL,
    logo_url varchar(2048),
    site_url varchar(2048),
    ordem integer NOT NULL DEFAULT 0 CONSTRAINT ck_apoiadores_ordem CHECK (ordem >= 0),
    publicado boolean NOT NULL DEFAULT false,
    criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    atualizado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX ix_apoiadores_hackathon ON apoiadores(hackathon_id, categoria, ordem);

CREATE TABLE faq_itens (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id uuid NOT NULL REFERENCES hackathon(id),
    pergunta varchar(500) NOT NULL,
    resposta text NOT NULL,
    ordem integer NOT NULL DEFAULT 0 CONSTRAINT ck_faq_itens_ordem CHECK (ordem >= 0),
    publicado boolean NOT NULL DEFAULT false,
    criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    atualizado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX ix_faq_itens_hackathon ON faq_itens(hackathon_id, ordem);

-- Fases extras do cronograma; as datas do próprio edital (inscrições, propostas...) vêm de `hackathon`
CREATE TABLE fases_cronograma (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id uuid NOT NULL REFERENCES hackathon(id),
    nome varchar(255) NOT NULL,
    descricao text,
    inicio timestamp NOT NULL,
    fim timestamp NOT NULL,
    publicado boolean NOT NULL DEFAULT false,
    criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    atualizado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT ck_fases_cronograma_periodo CHECK (fim >= inicio)
);
CREATE INDEX ix_fases_cronograma_hackathon ON fases_cronograma(hackathon_id, inicio);

CREATE TABLE sessoes_treinamento (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id uuid NOT NULL REFERENCES hackathon(id),
    titulo varchar(255) NOT NULL,
    descricao text,
    inicio timestamp NOT NULL,
    fim timestamp,
    local varchar(255),
    link_url varchar(2048),
    publicado boolean NOT NULL DEFAULT false,
    criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    atualizado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT ck_sessoes_treinamento_periodo CHECK (fim IS NULL OR fim >= inicio),
    CONSTRAINT ck_sessoes_treinamento_onde CHECK (local IS NOT NULL OR link_url IS NOT NULL)
);
CREATE INDEX ix_sessoes_treinamento_hackathon ON sessoes_treinamento(hackathon_id, inicio);

CREATE TABLE materiais_treinamento (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    sessao_id uuid NOT NULL REFERENCES sessoes_treinamento(id) ON DELETE CASCADE,
    titulo varchar(255) NOT NULL,
    url varchar(2048) NOT NULL,
    ordem integer NOT NULL DEFAULT 0 CONSTRAINT ck_materiais_treinamento_ordem CHECK (ordem >= 0),
    criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX ix_materiais_treinamento_sessao ON materiais_treinamento(sessao_id, ordem);

COMMENT ON COLUMN hackathon.descricao IS 'Texto da página pública da edição (RF10)';
COMMENT ON COLUMN termos.rascunho IS 'Versão ainda não publicada: editável e excluível; publicada, é imutável';
COMMENT ON TABLE materiais_treinamento IS 'Somente links (RNF20): a API não recebe nem guarda arquivos';
