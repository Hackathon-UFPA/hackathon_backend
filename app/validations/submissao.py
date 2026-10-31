from datetime import UTC, datetime

from app.models import Hackathon, Submissao
from app.validations.inscricao import como_utc


def propostas_abertas(hackathon: Hackathon, agora: datetime | None = None) -> bool:
    """O envio exige os dois limites do prazo, independentemente do prazo de inscrições."""
    inicio, fim = hackathon.propostas_inicio, hackathon.propostas_fim
    if inicio is None or fim is None:
        return False
    return como_utc(inicio) <= como_utc(agora or datetime.now(UTC)) <= como_utc(fim)


def campos_obrigatorios_pendentes(proposta: Submissao) -> list[str]:
    campos = []
    if proposta.tema_id is None:
        campos.append("tema_id")
    for campo in ("titulo", "descricao", "bases_dados"):
        valor = getattr(proposta, campo)
        if not valor or not valor.strip():
            campos.append(campo)
    if not proposta.ods or any(ods is None or not 1 <= ods <= 17 for ods in proposta.ods):
        campos.append("ods")
    return campos
