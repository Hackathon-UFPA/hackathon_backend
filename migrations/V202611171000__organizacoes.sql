-- Plataforma multi-organização: empresas e instituições de ensino organizam os próprios
-- hackathons.
--
-- * `organizacoes`: quem promove hackathons. Nasce no cadastro público de organização, junto
--   com o primeiro Organizador.
-- * `usuarios.organizacao_id`: equipe interna da organização (Organizador, Comitê Científico,
--   Comitê Técnico, Mentor). Participante e DEV não pertencem a organização.
-- * `hackathon.organizacao_id`: dona da edição. Organizador e Comitê só gerenciam as edições da
--   própria organização.
-- * `hackathon.local`: onde acontece, para a página pública (a `descricao` já vem da
--   V202611161100).
--
-- Dados que já existiam (a edição da UFPA) passam para uma organização criada aqui, junto com
-- os usuários de equipe interna, para continuarem funcionando.

CREATE TYPE tipo_organizacao AS ENUM ('EMPRESA', 'INSTITUICAO_ENSINO', 'OUTRO');

CREATE TABLE organizacoes (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    nome          varchar(255) NOT NULL,
    tipo          tipo_organizacao NOT NULL,
    site          varchar(255),
    descricao     text,
    criado_em     timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    atualizado_em timestamp
);

ALTER TABLE usuarios ADD COLUMN organizacao_id uuid REFERENCES organizacoes (id);
ALTER TABLE hackathon ADD COLUMN organizacao_id uuid REFERENCES organizacoes (id);
ALTER TABLE hackathon ADD COLUMN local varchar(255);

CREATE INDEX idx_usuarios_organizacao_id ON usuarios (organizacao_id);
CREATE INDEX idx_hackathon_organizacao_id ON hackathon (organizacao_id);

DO $$
DECLARE
    org uuid;
BEGIN
    IF EXISTS (SELECT 1 FROM hackathon)
       OR EXISTS (SELECT 1 FROM usuarios WHERE papel NOT IN ('PARTICIPANTE', 'DEV')) THEN
        INSERT INTO organizacoes (nome, tipo)
        VALUES ('Universidade Federal do Pará', 'INSTITUICAO_ENSINO')
        RETURNING id INTO org;

        UPDATE hackathon SET organizacao_id = org;
        UPDATE usuarios SET organizacao_id = org WHERE papel NOT IN ('PARTICIPANTE', 'DEV');
    END IF;
END $$;

COMMENT ON TABLE organizacoes IS
    'Empresas e instituições de ensino que organizam hackathons na plataforma.';
COMMENT ON COLUMN usuarios.organizacao_id IS
    'Organização da equipe interna (Organizador, Comitês, Mentor). NULL para Participante e DEV.';
COMMENT ON COLUMN hackathon.organizacao_id IS 'Organização dona da edição.';
