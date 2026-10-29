from datetime import UTC, datetime

from app.const.enums import StatusHackathon
from app.models import Hackathon


def como_utc(momento: datetime) -> datetime:
    """As colunas de data são `timestamp` em UTC. Conforme a versão do driver, voltam com ou
    sem fuso; comparar exige os dois lados no mesmo formato."""
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def inscricoes_abertas(hackathon: Hackathon, agora: datetime | None = None) -> bool:
    """RN06: o status precisa ser INSCRICOES e, quando o edital define datas, o momento atual
    tem de estar dentro delas."""
    if hackathon.status != StatusHackathon.INSCRICOES:
        return False
    agora_utc = como_utc(agora or datetime.now(UTC))
    inicio, fim = hackathon.inscricoes_inicio, hackathon.inscricoes_fim
    if inicio is not None and agora_utc < como_utc(inicio):
        return False
    return not (fim is not None and agora_utc > como_utc(fim))
