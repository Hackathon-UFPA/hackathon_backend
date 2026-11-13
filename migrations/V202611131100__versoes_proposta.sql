-- BE-S5-09 (RF26 a RF28, RN07, RN08): reenvio da proposta com histórico e protocolo por versão.
--
-- Cada envio definitivo (o primeiro e cada reenvio) vira uma linha imutável em
-- versoes_proposta, com o conteúdo enviado e o próprio protocolo. A linha de `submissoes`
-- continua sendo a proposta da equipe e guarda sempre o conteúdo da versão mais recente,
-- que é a avaliada.

CREATE TABLE versoes_proposta (
    id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    submissao_id  uuid NOT NULL REFERENCES submissoes (id) ON DELETE CASCADE,
    numero        smallint NOT NULL,
    tema_id       uuid REFERENCES temas (id),
    titulo        varchar,
    descricao     text,
    ods           smallint[],
    bases_dados   text,
    documento_url varchar,
    -- Excluir o protocolo exclui a versão: uma versão sem protocolo não vale como envio.
    protocolo_id  uuid NOT NULL REFERENCES protocolos (id) ON DELETE CASCADE,
    enviada_por   uuid REFERENCES usuarios (id),
    enviada_em    timestamp NOT NULL,
    CONSTRAINT uq_versoes_proposta_numero UNIQUE (submissao_id, numero),
    CONSTRAINT uq_versoes_proposta_protocolo UNIQUE (protocolo_id),
    CONSTRAINT ck_versoes_proposta_numero CHECK (numero >= 1)
);

CREATE INDEX idx_versoes_proposta_submissao ON versoes_proposta (submissao_id);

COMMENT ON TABLE versoes_proposta IS 'Histórico imutável dos envios da proposta (BE-S5-09); numero 1 é o envio original';

-- Propostas já enviadas viram a versão 1, com o protocolo que já tinham. Enviadas sem
-- protocolo (dado legado) ficam como estão: não se inventa protocolo.
INSERT INTO versoes_proposta (
    submissao_id, numero, tema_id, titulo, descricao, ods, bases_dados, documento_url,
    protocolo_id, enviada_por, enviada_em
)
SELECT s.id, 1, s.tema_id, s.titulo, s.descricao, s.ods, s.bases_dados, s.documento_url,
       p.id, p.emitido_por, COALESCE(s.enviado_em, p.emitido_em)
FROM submissoes s
JOIN protocolos p ON p.submissao_id = s.id AND p.tipo = 'PROPOSTA'
WHERE s.status = 'ENVIADA';

-- O protocolo passa a ser único por versão (uq_versoes_proposta_protocolo), não por proposta.
DROP INDEX uq_protocolos_proposta_submissao;

-- Versão enviada não muda. Excluir continua possível (cascata da proposta ou do protocolo).
CREATE FUNCTION fn_versao_proposta_imutavel() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'versao_proposta_imutavel: a versão % da proposta já foi enviada', OLD.numero
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_versoes_proposta_imutavel
    BEFORE UPDATE ON versoes_proposta
    FOR EACH ROW EXECUTE FUNCTION fn_versao_proposta_imutavel();
