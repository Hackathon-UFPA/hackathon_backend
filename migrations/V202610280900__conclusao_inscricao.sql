-- BE-S4-05: conclusão da inscrição e homologação da equipe.
-- Requisitos: RF21, RF22, RF23, RF25; regras RN01, RN03, RN05, RN06, RN25.
-- As regras de contagem, prazo e perfil continuam no service. O banco só garante que a
-- conclusão da inscrição emite um único protocolo por equipe, mesmo com pedidos simultâneos.

CREATE UNIQUE INDEX uq_protocolos_inscricao_equipe ON protocolos (equipe_id)
    WHERE tipo = 'INSCRICAO_EQUIPE';
