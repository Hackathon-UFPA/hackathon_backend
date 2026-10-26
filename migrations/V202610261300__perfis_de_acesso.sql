-- Perfis de acesso conforme a seção 3 e o RF06 do documento de requisitos (Sprint 3).
-- PROFESSOR, COORDENADOR e AVALIADOR saem; os comitês passam a ser papéis separados (RN11).
-- Líder técnico não é papel: fica em membros_equipe.funcao = 'LIDER' (vale por equipe).

-- O Postgres não remove valores de enum: o tipo é recriado.
-- Não há mapeamento óbvio dos papéis antigos, então a migration para se algum usuário ainda os usar.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM usuarios WHERE papel IN ('PROFESSOR', 'COORDENADOR', 'AVALIADOR')) THEN
        RAISE EXCEPTION 'Há usuários com papel PROFESSOR, COORDENADOR ou AVALIADOR; '
            'atualize-os para ORGANIZADOR, COMITE_CIENTIFICO ou COMITE_TECNICO antes desta migration';
    END IF;
END
$$;

ALTER TYPE papel_usuario RENAME TO papel_usuario_antigo;

CREATE TYPE papel_usuario AS ENUM ('PARTICIPANTE', 'MENTOR', 'COMITE_TECNICO', 'COMITE_CIENTIFICO', 'ORGANIZADOR', 'DEV');

ALTER TABLE usuarios ALTER COLUMN papel TYPE papel_usuario USING papel::text::papel_usuario;

DROP TYPE papel_usuario_antigo;

-- Usuário desativado pelo Organizador (RF07) e dados do perfil Mentor (RF37, RV09)
ALTER TABLE usuarios
    ADD COLUMN ativo            boolean NOT NULL DEFAULT true,
    ADD COLUMN empresa_parceira varchar,
    ADD COLUMN area_atuacao     varchar,
    ADD COLUMN max_equipes      smallint CONSTRAINT ck_usuarios_max_equipes CHECK (max_equipes > 0);

COMMENT ON COLUMN usuarios.empresa_parceira IS 'Mentor: empresa parceira que o indicou';
COMMENT ON COLUMN usuarios.max_equipes IS 'Mentor: quantidade máxima de equipes acompanhadas';
