-- BE-S5-04 (RF19, RF22, RF28, RF33, RF38, RF53, RF60, RF61): central de notificações in-app.
-- Tabela genérica por destinatário, com leitura e idempotência. O RF33 continua em
-- notificacoes_resultado (status de envio e pareceres); cada aviso de resultado ganha uma linha aqui.
CREATE TYPE tipo_notificacao AS ENUM (
    'CONVITE', 'ACEITE', 'INSCRICAO', 'PROPOSTA', 'RESULTADO', 'MENTOR', 'CHAT', 'PRAZO'
);

CREATE TABLE notificacoes (
    id                        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    usuario_id                uuid NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    tipo                      tipo_notificacao NOT NULL,
    titulo                    text NOT NULL,
    mensagem                  text NOT NULL,
    dados                     jsonb,
    referencia_tipo           text,
    referencia_id             uuid,
    chave_idempotencia        text NOT NULL,
    notificacao_resultado_id  uuid REFERENCES notificacoes_resultado (id) ON DELETE CASCADE,
    criado_em                 timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    lida_em                   timestamp,
    CONSTRAINT uq_notificacoes_usuario_chave UNIQUE (usuario_id, chave_idempotencia),
    CONSTRAINT uq_notificacoes_resultado UNIQUE (notificacao_resultado_id),
    CONSTRAINT ck_notificacoes_chave CHECK (length(chave_idempotencia) > 0),
    CONSTRAINT ck_notificacoes_referencia CHECK ((referencia_tipo IS NULL) = (referencia_id IS NULL)),
    -- O aviso de resultado sempre aponta para a linha do RF33 que o originou
    CONSTRAINT ck_notificacoes_resultado CHECK ((tipo = 'RESULTADO') = (notificacao_resultado_id IS NOT NULL))
);

-- Listagem do usuário (mais recentes primeiro) e contagem de não lidas
CREATE INDEX idx_notificacoes_usuario_criado ON notificacoes (usuario_id, criado_em DESC, id);
CREATE INDEX idx_notificacoes_nao_lidas ON notificacoes (usuario_id) WHERE lida_em IS NULL;

COMMENT ON TABLE notificacoes IS
    'Central de notificações in-app: uma linha por destinatário e fato. Só o próprio usuário as vê.';
COMMENT ON COLUMN notificacoes.chave_idempotencia IS
    'Mesmo usuário e mesma chave, mesmo fato: a segunda gravação é ignorada';
COMMENT ON COLUMN notificacoes.dados IS 'Detalhes opcionais do fato (ids, resposta do convite etc.)';
COMMENT ON COLUMN notificacoes.referencia_tipo IS 'Tipo do objeto de origem (ex.: CONVITE, HOMOLOGACAO)';
COMMENT ON COLUMN notificacoes.lida_em IS 'NULL enquanto não lida; marcar de novo não altera o valor';

-- Histórico do RF33 (canal PLATAFORMA): entra como lido, para não inflar o contador de não lidas
INSERT INTO notificacoes (
    usuario_id, tipo, titulo, mensagem, dados, referencia_tipo, referencia_id,
    chave_idempotencia, notificacao_resultado_id, criado_em, lida_em
)
SELECT n.usuario_id, 'RESULTADO', 'Resultado do hackathon', n.mensagem,
       jsonb_build_object(
           'aprovada', n.aprovada, 'hackathon_id', n.hackathon_id,
           'equipe_id', n.equipe_id, 'submissao_id', n.submissao_id
       ),
       'HOMOLOGACAO', n.homologacao_id,
       'resultado:' || n.homologacao_id::text || ':' || n.equipe_id::text,
       n.id, n.criado_em, n.criado_em
FROM notificacoes_resultado n
WHERE n.canal = 'PLATAFORMA';

-- Eventos de mentoria ainda não publicados na plataforma (BE-S5-11), também como lidos
INSERT INTO notificacoes (
    usuario_id, tipo, titulo, mensagem, dados, referencia_tipo, referencia_id,
    chave_idempotencia, criado_em, lida_em
)
SELECT e.usuario_id, 'MENTOR', 'Mentoria da equipe', e.mensagem,
       jsonb_build_object('atribuicao_id', e.atribuicao_id, 'evento', e.tipo,
                          'equipe_id', a.equipe_id),
       'ATRIBUICAO_MENTOR', e.atribuicao_id,
       'mentoria:' || e.atribuicao_id::text || ':' || e.tipo,
       e.criado_em, e.criado_em
FROM eventos_notificacao_mentoria e
JOIN atribuicoes_mentor a ON a.id = e.atribuicao_id
WHERE e.publicado_na_plataforma_em IS NULL;

UPDATE eventos_notificacao_mentoria SET publicado_na_plataforma_em = (now() AT TIME ZONE 'utc')
WHERE publicado_na_plataforma_em IS NULL;
