from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import SituacaoEquipe


class EquipeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hackathon_id: UUID
    nome: str | None = Field(default=None, max_length=255, examples=["Equipe Backend"])


class EquipeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(default=None, max_length=255)


class EquipeResponse(EquipeCreate):
    id: UUID
    # Controlada pelo sistema (RF22, RF23), não pelo cliente
    situacao: SituacaoEquipe
    inscricao_concluida_em: datetime | None = None
    homologada_em: datetime | None = None
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
