-- Migration inicial (versão base do Flyway).
-- Novas migrations: migrations/V<AAAAMMDDHHMM>__descricao.sql
-- Nunca edite uma migration já aplicada; crie uma nova.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enums
CREATE TYPE papel_usuario AS ENUM ('PARTICIPANTE', 'PROFESSOR', 'COORDENADOR', 'AVALIADOR', 'MENTOR', 'DEV');

CREATE TYPE status_hackathon AS ENUM ('RASCUNHO', 'INSCRICOES', 'INSCRICOES_ENCERRADAS', 'ATIVO', 'EM_AVALIACAO', 'FINALIZADO', 'CANCELADO');

CREATE TYPE funcao_membro AS ENUM ('LIDER', 'DESENVOLVEDOR', 'DESIGNER', 'NEGOCIOS', 'OUTRO');

CREATE TYPE categoria_artefato AS ENUM ('REPOSITORIO_CODIGO', 'DIAGRAMA', 'VIDEO', 'APRESENTACAO', 'DOCUMENTACAO', 'PROTOTIPO', 'OUTRO');

-- Tabelas
CREATE TABLE usuarios (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    nome          varchar,
    email         varchar UNIQUE NOT NULL,
    papel         papel_usuario NOT NULL,
    criado_em     timestamp,
    atualizado_em timestamp
);

CREATE TABLE hackathon (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    nome        varchar,
    tema        varchar,
    data_inicio timestamp,
    data_fim    timestamp,
    status      status_hackathon DEFAULT 'INSCRICOES'
);

CREATE TABLE equipes (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    hackathon_id  uuid NOT NULL REFERENCES hackathon (id),
    nome          varchar,
    criado_em     timestamp,
    atualizado_em timestamp
);

CREATE TABLE membros_equipe (
    equipe_id  uuid NOT NULL REFERENCES equipes (id),
    usuario_id uuid NOT NULL REFERENCES usuarios (id),
    funcao     funcao_membro,
    PRIMARY KEY (equipe_id, usuario_id)
);

CREATE TABLE artefatos (
    id        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipe_id uuid NOT NULL REFERENCES equipes (id),
    nome      varchar NOT NULL,
    categoria categoria_artefato NOT NULL,
    url       varchar NOT NULL,
    criado_em timestamp
);

COMMENT ON COLUMN artefatos.url IS 'URL externa(ex:cloudinary, github)';

CREATE TABLE submissoes (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipe_id    uuid NOT NULL REFERENCES equipes (id),
    hackathon_id uuid NOT NULL REFERENCES hackathon (id),
    titulo       varchar,
    descricao    text,
    enviado_em   timestamp
);

CREATE TABLE avaliacoes (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    submissao_id uuid NOT NULL REFERENCES submissoes (id),
    avaliador_id uuid NOT NULL REFERENCES usuarios (id),
    nota         decimal,
    comentarios  text,
    avaliado_em  timestamp
);

-- Índices nas FKs
CREATE INDEX idx_equipes_hackathon_id ON equipes (hackathon_id);
CREATE INDEX idx_membros_equipe_usuario_id ON membros_equipe (usuario_id);
CREATE INDEX idx_artefatos_equipe_id ON artefatos (equipe_id);
CREATE INDEX idx_submissoes_equipe_id ON submissoes (equipe_id);
CREATE INDEX idx_submissoes_hackathon_id ON submissoes (hackathon_id);
CREATE INDEX idx_avaliacoes_submissao_id ON avaliacoes (submissao_id);
CREATE INDEX idx_avaliacoes_avaliador_id ON avaliacoes (avaliador_id);
