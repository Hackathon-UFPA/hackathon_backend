from decimal import Decimal

from app.const.enums import FaseRubrica

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

# Mínimos por fase (BE-S5-08). PENDENTE: a RN10 não separa as fases; até o time definir os
# mínimos do projeto final, as duas rubricas exigem a mesma lista provisória.
CRITERIOS_MINIMOS_POR_FASE: dict[FaseRubrica, tuple[str, ...]] = {
    FaseRubrica.PROPOSTA: CRITERIOS_MINIMOS_RN10,
    FaseRubrica.PROJETO_FINAL: CRITERIOS_MINIMOS_RN10,
}
