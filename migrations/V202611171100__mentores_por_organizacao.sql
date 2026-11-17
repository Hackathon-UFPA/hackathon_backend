-- Mentores passam a pertencer à organização do hackathon para o qual foram convidados: só a
-- equipe interna dessa organização os gerencia e atribui às equipes.
--
-- Os mentores cadastrados antes desta mudança ficaram sem organização. Eles herdam a do
-- hackathon do convite mais recente. Quem não tem convite continua sem organização (só DEV o
-- vê), como os demais dados antigos.

UPDATE usuarios u
SET organizacao_id = ultimo.organizacao_id
FROM (
    SELECT DISTINCT ON (c.usuario_id) c.usuario_id, h.organizacao_id
    FROM convites_mentor c
    JOIN hackathon h ON h.id = c.hackathon_id
    WHERE h.organizacao_id IS NOT NULL
    ORDER BY c.usuario_id, c.criado_em DESC
) ultimo
WHERE u.id = ultimo.usuario_id
  AND u.papel = 'MENTOR'
  AND u.organizacao_id IS NULL;
