-- BE-S5-01 (RF01, RF18, RF21 a RF24, RN01, RN02, RN03, RN05, RN25): equipes por categoria.
-- Decisão de 05/11: o líder informa a composição inteira em uma operação, com categoria
-- ESTUDANTES, PROFISSIONAIS ou MISTA. Dois tipos de dado ficam separados:
--   * indicado pelo líder: categoria da equipe e `tipo_integrante` de cada pessoa (convite e vínculo);
--   * confirmado por cada pessoa, na própria conta: dados pessoais, aceite dos termos e comprovante.
-- Equipes, convites e vínculos que já existem eram todos acadêmicos: entram como ESTUDANTES/ESTUDANTE.
CREATE TYPE categoria_equipe AS ENUM ('ESTUDANTES', 'PROFISSIONAIS', 'MISTA');
CREATE TYPE tipo_integrante AS ENUM ('ESTUDANTE', 'PROFISSIONAL');

ALTER TABLE equipes
    ADD COLUMN categoria categoria_equipe NOT NULL DEFAULT 'ESTUDANTES';

ALTER TABLE convites
    ADD COLUMN tipo_integrante tipo_integrante NOT NULL DEFAULT 'ESTUDANTE';
ALTER TABLE membros_equipe
    ADD COLUMN tipo_integrante tipo_integrante NOT NULL DEFAULT 'ESTUDANTE';

COMMENT ON COLUMN equipes.categoria IS 'Indicada pelo líder (decisão de 05/11); legado = ESTUDANTES';
COMMENT ON COLUMN convites.tipo_integrante IS 'Indicado pelo líder; a pessoa não o altera';
COMMENT ON COLUMN membros_equipe.tipo_integrante IS 'Copiado do convite no aceite; o líder indica o seu';

-- Política de elegibilidade provisória, por edição, até o Squad 1 validar (o documento da Sprint 2
-- previa só graduandos). O padrão libera as três categorias; o Organizador restringe se precisar.
ALTER TABLE hackathon
    ADD COLUMN aceita_equipe_estudantes    boolean NOT NULL DEFAULT true,
    ADD COLUMN aceita_equipe_profissionais boolean NOT NULL DEFAULT true,
    ADD COLUMN aceita_equipe_mista         boolean NOT NULL DEFAULT true,
    ADD CONSTRAINT ck_hackathon_categorias
        CHECK (aceita_equipe_estudantes OR aceita_equipe_profissionais OR aceita_equipe_mista);

COMMENT ON COLUMN hackathon.aceita_equipe_estudantes IS 'Política provisória de elegibilidade (Squad 1): aceita equipes ESTUDANTES';
COMMENT ON COLUMN hackathon.aceita_equipe_profissionais IS 'Política provisória de elegibilidade (Squad 1): aceita equipes PROFISSIONAIS';
COMMENT ON COLUMN hackathon.aceita_equipe_mista IS 'Política provisória de elegibilidade (Squad 1): aceita equipes MISTA';
