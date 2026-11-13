from enum import StrEnum


class CodigoPendenciaResultado(StrEnum):
    """O que impede homologar o resultado da avaliação (RF31).

    Fica fora de `enums.py` de propósito: aquele arquivo espelha só os tipos do Postgres.
    """

    QUANTIDADE_NAO_CONFIGURADA = "QUANTIDADE_NAO_CONFIGURADA"
    SEM_PROPOSTAS = "SEM_PROPOSTAS"
    AVALIADORES_INSUFICIENTES = "AVALIADORES_INSUFICIENTES"
    AVALIACAO_PENDENTE = "AVALIACAO_PENDENTE"
    # BE-S5-09: homologar antes do fim do prazo de propostas deixaria de fora envios válidos
    PRAZO_DE_PROPOSTAS_ABERTO = "PRAZO_DE_PROPOSTAS_ABERTO"
    # BE-S5-09: avaliação marcada como enviada sem tudo o que a RF30 exige (inclui legado)
    AVALIACAO_INCOMPLETA = "AVALIACAO_INCOMPLETA"
