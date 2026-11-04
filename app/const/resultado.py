from enum import StrEnum


class CodigoPendenciaResultado(StrEnum):
    """O que impede homologar o resultado da avaliação (RF31).

    Fica fora de `enums.py` de propósito: aquele arquivo espelha só os tipos do Postgres.
    """

    QUANTIDADE_NAO_CONFIGURADA = "QUANTIDADE_NAO_CONFIGURADA"
    SEM_PROPOSTAS = "SEM_PROPOSTAS"
    AVALIADORES_INSUFICIENTES = "AVALIADORES_INSUFICIENTES"
    AVALIACAO_PENDENTE = "AVALIACAO_PENDENTE"
