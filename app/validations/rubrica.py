import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from app.const.rubrica import CRITERIOS_MINIMOS_RN10, SOMA_PESOS
from app.validations.inscricao import como_utc


def normalizar_nome(nome: str) -> str:
    """Compara nomes de critério sem diferenciar maiúsculas, acentos e espaços extras."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def soma_dos_pesos(pesos: Iterable[Decimal]) -> Decimal:
    return sum(pesos, Decimal("0"))


def criterios_minimos_faltantes(
    nomes: Iterable[str], minimos: Iterable[str] = CRITERIOS_MINIMOS_RN10
) -> list[str]:
    presentes = {normalizar_nome(nome) for nome in nomes}
    return [minimo for minimo in minimos if normalizar_nome(minimo) not in presentes]


def pendencias_para_publicar(
    nomes: list[str], pesos: list[Decimal], minimos: Iterable[str] = CRITERIOS_MINIMOS_RN10
) -> list[str]:
    """Problemas de conteúdo que impedem publicar a rubrica (RF16, RN10)."""
    pendencias = []
    if not nomes:
        pendencias.append("A rubrica precisa de pelo menos um critério.")
    soma = soma_dos_pesos(pesos)
    if soma != SOMA_PESOS:
        pendencias.append(f"A soma dos pesos deve ser {SOMA_PESOS}%; está em {soma}%.")
    faltantes = criterios_minimos_faltantes(nomes, minimos)
    if faltantes:
        pendencias.append(f"Critérios obrigatórios da RN10 ausentes: {', '.join(faltantes)}.")
    return pendencias


def pode_publicar_no_prazo(inscricoes_inicio: datetime | None, agora: datetime | None = None):
    """A rubrica precisa estar pública antes de as inscrições abrirem (RF17)."""
    if inscricoes_inicio is None:
        return True
    return como_utc(agora or datetime.now(UTC)) < como_utc(inscricoes_inicio)
