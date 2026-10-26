-- BE-S4-01: fluxos de inscrição da equipe e de proposta (Fase 1).
-- Requisitos: RF18 a RF23, RF26 a RF28; regras RN01 a RN07, RN25, RN30.
-- Regras que dependem de contagem, prazo ou perfil (3 a 5 integrantes, homologação
-- automática, bloqueio após o prazo) ficam na camada de serviço, não no banco.

-- Enums
CREATE TYPE situacao_equipe AS ENUM ('EM_FORMACAO', 'AGUARDANDO_HOMOLOGACAO', 'HOMOLOGADA', 'NAO_HOMOLOGADA');

CREATE TYPE status_convite AS ENUM ('PENDENTE', 'ACEITO', 'RECUSADO', 'CANCELADO');

CREATE TYPE tipo_termo AS ENUM ('REGULAMENTO', 'TERMO_CONSENTIMENTO');

CREATE TYPE status_comprovante AS ENUM ('PENDENTE', 'APROVADO', 'RECUSADO');

CREATE TYPE status_proposta AS ENUM ('RASCUNHO', 'ENVIADA');

CREATE TYPE tipo_protocolo AS ENUM ('INSCRICAO_EQUIPE', 'PROPOSTA');

-- Usuários: dados complementares de inscrição (RF01)
ALTER TABLE usuarios
    ADD COLUMN instituicao varchar,
    ADD COLUMN curso       varchar,
    ADD COLUMN periodo     smallint CONSTRAINT ck_usuarios_periodo CHECK (periodo > 0);

-- Hackathon: tamanho da equipe (RN01, ainda a confirmar na Q04) e prazos da Fase 1 (RN06, RN07, RN30)
ALTER TABLE hackathon
    ADD COLUMN min_integrantes   smallint NOT NULL DEFAULT 3,
    ADD COLUMN max_integrantes   smallint NOT NULL DEFAULT 5,
    ADD COLUMN inscricoes_inicio timestamp,
    ADD COLUMN inscricoes_fim    timestamp,
    ADD COLUMN homologacao_fim   timestamp,
    ADD COLUMN propostas_inicio  timestamp,
    ADD COLUMN propostas_fim     timestamp,
    ADD CONSTRAINT ck_hackathon_integrantes CHECK (min_integrantes >= 1 AND min_integrantes <= max_integrantes),
    ADD CONSTRAINT ck_hackathon_inscricoes CHECK (inscricoes_fim > inscricoes_inicio),
    ADD CONSTRAINT ck_hackathon_homologacao CHECK (homologacao_fim >= inscricoes_fim),
    ADD CONSTRAINT ck_hackathon_propostas CHECK (propostas_fim > propostas_inicio);

-- Equipes: situação no ciclo de vida da Fase 1 (RF22, RF23)
ALTER TABLE equipes
    ADD COLUMN situacao               situacao_equipe NOT NULL DEFAULT 'EM_FORMACAO',
    ADD COLUMN inscricao_concluida_em timestamp,
    ADD COLUMN homologada_em          timestamp,
    -- Alvo das FKs compostas que garantem que registros ligados à equipe são do mesmo hackathon
    ADD CONSTRAINT uq_equipes_id_hackathon UNIQUE (id, hackathon_id);

-- Membros: uma equipe por pessoa em cada edição (RN02) e um único líder por equipe (RN01)
ALTER TABLE membros_equipe ADD COLUMN hackathon_id uuid;

UPDATE membros_equipe m
SET hackathon_id = e.hackathon_id
FROM equipes e
WHERE e.id = m.equipe_id;

ALTER TABLE membros_equipe
    ALTER COLUMN hackathon_id SET NOT NULL,
    ADD COLUMN entrou_em timestamp DEFAULT (now() AT TIME ZONE 'utc'),
    ADD CONSTRAINT fk_membros_equipe_equipe_hackathon
        FOREIGN KEY (equipe_id, hackathon_id) REFERENCES equipes (id, hackathon_id),
    ADD CONSTRAINT uq_membros_equipe_hackathon_usuario UNIQUE (hackathon_id, usuario_id);

CREATE UNIQUE INDEX uq_membros_equipe_lider ON membros_equipe (equipe_id) WHERE funcao = 'LIDER';

-- Temas do edital (RF15, RN04)
CREATE TABLE temas (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id  uuid NOT NULL REFERENCES hackathon (id),
    titulo        varchar NOT NULL,
    descricao     text,
    contexto      text,
    ods           smallint[] NOT NULL DEFAULT '{}',
    ativo         boolean NOT NULL DEFAULT true,
    criado_em     timestamp DEFAULT (now() AT TIME ZONE 'utc'),
    atualizado_em timestamp,
    CONSTRAINT uq_temas_hackathon_titulo UNIQUE (hackathon_id, titulo),
    CONSTRAINT uq_temas_id_hackathon UNIQUE (id, hackathon_id),
    CONSTRAINT ck_temas_ods CHECK (ods <@ '{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17}'::smallint[])
);

COMMENT ON COLUMN temas.ods IS 'Números dos ODS da ONU relacionados (1 a 17)';

-- Convites: o líder informa nome e e-mail; a pessoa confirma ou recusa (RF18, RF19)
CREATE TABLE convites (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipe_id     uuid NOT NULL REFERENCES equipes (id),
    nome          varchar NOT NULL,
    email         varchar NOT NULL,
    usuario_id    uuid REFERENCES usuarios (id),
    convidado_por uuid NOT NULL REFERENCES usuarios (id),
    status        status_convite NOT NULL DEFAULT 'PENDENTE',
    token         uuid NOT NULL DEFAULT uuid_generate_v4(),
    enviado_em    timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    respondido_em timestamp,
    CONSTRAINT uq_convites_token UNIQUE (token),
    CONSTRAINT ck_convites_resposta CHECK (status NOT IN ('ACEITO', 'RECUSADO') OR respondido_em IS NOT NULL)
);

COMMENT ON COLUMN convites.usuario_id IS 'Preenchido quando a pessoa convidada já tem (ou cria) conta';

-- Recusado/cancelado libera a vaga: só impede convite repetido ainda em aberto ou aceito
CREATE UNIQUE INDEX uq_convites_equipe_email_ativo ON convites (equipe_id, lower(email))
    WHERE status IN ('PENDENTE', 'ACEITO');

-- Regulamento e termo de consentimento, versionados (RF11, RF20)
CREATE TABLE termos (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id uuid NOT NULL REFERENCES hackathon (id),
    tipo         tipo_termo NOT NULL,
    versao       varchar NOT NULL,
    titulo       varchar NOT NULL,
    conteudo     text,
    url          varchar,
    vigente      boolean NOT NULL DEFAULT false,
    publicado_em timestamp DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_termos_hackathon_tipo_versao UNIQUE (hackathon_id, tipo, versao),
    CONSTRAINT ck_termos_conteudo CHECK (conteudo IS NOT NULL OR url IS NOT NULL)
);

CREATE UNIQUE INDEX uq_termos_vigente ON termos (hackathon_id, tipo) WHERE vigente;

-- Aceite de cada versão de termo, com data e hora do servidor (RF20, RN05)
CREATE TABLE aceites_termos (
    id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    termo_id   uuid NOT NULL REFERENCES termos (id),
    usuario_id uuid NOT NULL REFERENCES usuarios (id),
    aceito_em  timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_aceites_termos_termo_usuario UNIQUE (termo_id, usuario_id)
);

-- Comprovante de vínculo conferido pelo Comitê Científico (RF21, RN25, RN30).
-- Cada reenvio após recusa é uma linha nova, preservando o histórico.
CREATE TABLE comprovantes_vinculo (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    usuario_id    uuid NOT NULL REFERENCES usuarios (id),
    hackathon_id  uuid NOT NULL REFERENCES hackathon (id),
    arquivo_url   varchar NOT NULL,
    status        status_comprovante NOT NULL DEFAULT 'PENDENTE',
    motivo_recusa text,
    enviado_em    timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    validado_por  uuid REFERENCES usuarios (id),
    validado_em   timestamp,
    CONSTRAINT ck_comprovantes_motivo CHECK (status <> 'RECUSADO' OR motivo_recusa IS NOT NULL),
    CONSTRAINT ck_comprovantes_validacao CHECK (status = 'PENDENTE' OR validado_em IS NOT NULL)
);

COMMENT ON COLUMN comprovantes_vinculo.arquivo_url IS 'URL externa do PDF (ex: cloudinary)';

CREATE UNIQUE INDEX uq_comprovantes_vinculo_ativo ON comprovantes_vinculo (usuario_id, hackathon_id)
    WHERE status <> 'RECUSADO';

-- Submissões passam a ser a proposta da equipe, com rascunho (RF26, RF27, RN04)
ALTER TABLE submissoes
    ADD COLUMN tema_id       uuid REFERENCES temas (id),
    ADD COLUMN status        status_proposta NOT NULL DEFAULT 'RASCUNHO',
    ADD COLUMN ods           smallint[],
    ADD COLUMN bases_dados   text,
    ADD COLUMN documento_url varchar,
    ADD COLUMN criado_em     timestamp DEFAULT (now() AT TIME ZONE 'utc'),
    ADD COLUMN atualizado_em timestamp,
    ADD CONSTRAINT uq_submissoes_equipe UNIQUE (equipe_id),
    ADD CONSTRAINT fk_submissoes_equipe_hackathon
        FOREIGN KEY (equipe_id, hackathon_id) REFERENCES equipes (id, hackathon_id),
    ADD CONSTRAINT fk_submissoes_tema_hackathon
        FOREIGN KEY (tema_id, hackathon_id) REFERENCES temas (id, hackathon_id),
    ADD CONSTRAINT ck_submissoes_ods CHECK (ods <@ '{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17}'::smallint[]),
    -- Rascunho pode ficar incompleto; a proposta enviada exige os campos obrigatórios
    ADD CONSTRAINT ck_submissoes_enviada CHECK (
        status = 'RASCUNHO' OR (
            tema_id IS NOT NULL
            AND titulo IS NOT NULL
            AND descricao IS NOT NULL
            AND ods IS NOT NULL AND cardinality(ods) >= 1
            AND bases_dados IS NOT NULL
            AND enviado_em IS NOT NULL
        )
    );

COMMENT ON COLUMN submissoes.atualizado_em IS 'Último salvamento do rascunho';
COMMENT ON COLUMN submissoes.documento_url IS 'URL externa do PDF anexo, quando exigido';

-- Protocolos de conclusão da inscrição e de envio da proposta (RF22, RF28)
CREATE SEQUENCE protocolos_numero_seq;

CREATE TABLE protocolos (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    numero       varchar NOT NULL
                 DEFAULT ('HK' || to_char(now() AT TIME ZONE 'utc', 'YYYY') || '-' || lpad(nextval('protocolos_numero_seq')::text, 6, '0')),
    tipo         tipo_protocolo NOT NULL,
    equipe_id    uuid NOT NULL REFERENCES equipes (id),
    submissao_id uuid REFERENCES submissoes (id),
    emitido_por  uuid REFERENCES usuarios (id),
    emitido_em   timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_protocolos_numero UNIQUE (numero),
    CONSTRAINT ck_protocolos_proposta CHECK (tipo <> 'PROPOSTA' OR submissao_id IS NOT NULL)
);

ALTER SEQUENCE protocolos_numero_seq OWNED BY protocolos.numero;

-- Índices nas FKs (as cobertas por UNIQUE/PK não precisam)
CREATE INDEX idx_convites_equipe_id ON convites (equipe_id);
CREATE INDEX idx_convites_usuario_id ON convites (usuario_id);
CREATE INDEX idx_convites_convidado_por ON convites (convidado_por);
CREATE INDEX idx_aceites_termos_usuario_id ON aceites_termos (usuario_id);
CREATE INDEX idx_comprovantes_vinculo_usuario_id ON comprovantes_vinculo (usuario_id);
CREATE INDEX idx_comprovantes_vinculo_hackathon_id ON comprovantes_vinculo (hackathon_id);
CREATE INDEX idx_comprovantes_vinculo_validado_por ON comprovantes_vinculo (validado_por);
CREATE INDEX idx_submissoes_tema_id ON submissoes (tema_id);
CREATE INDEX idx_protocolos_equipe_id ON protocolos (equipe_id);
CREATE INDEX idx_protocolos_submissao_id ON protocolos (submissao_id);
CREATE INDEX idx_protocolos_emitido_por ON protocolos (emitido_por);
