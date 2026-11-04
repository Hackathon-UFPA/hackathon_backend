from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import CanalNotificacao, StatusEnvioNotificacao
from app.schemas.resultado import ParecerResponse


class NotificacaoResultadoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hackathon_id: UUID
    equipe_id: UUID
    submissao_id: UUID
    aprovada: bool
    mensagem: str
    canal: CanalNotificacao
    status_envio: StatusEnvioNotificacao = Field(
        description="PENDENTE, ENVIADO ou FALHA (com `erro`). Na plataforma nasce ENVIADO."
    )
    enviado_em: datetime | None = None
    erro: str | None = None
    criado_em: datetime
    pareceres: list[ParecerResponse] = Field(
        description="Pareceres anônimos dos avaliadores sobre a proposta da equipe"
    )
