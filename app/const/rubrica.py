from decimal import Decimal

# A soma dos pesos dos critérios precisa dar 100% para publicar (RF16)
SOMA_PESOS = Decimal("100")

# Critérios que toda rubrica precisa ter para ser publicada (RN10).
# PENDENTE: a lista oficial da RN10 ainda não foi confirmada pelo time; estes nomes são
# provisórios. A comparação ignora maiúsculas, acentos e espaços nas pontas.
CRITERIOS_MINIMOS_RN10: tuple[str, ...] = (
    "Inovação",
    "Impacto",
    "Viabilidade técnica",
    "Aderência ao tema",
)
