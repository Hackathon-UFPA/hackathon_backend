-- BE-S4-08 (RF28): a sequência gera o número único; este índice impede
-- emitir mais de um protocolo para a mesma proposta, inclusive fora da API.
CREATE UNIQUE INDEX uq_protocolos_proposta_submissao ON protocolos (submissao_id)
    WHERE tipo = 'PROPOSTA';
