from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EquipeCreate(BaseModel):
    hackathon_id: UUID
    nome: str | None = Field(default=None, max_length=255, examples=["Equipe Backend"])


class EquipeUpdate(BaseModel):
    nome: str | None = Field(default=None, max_length=255)


class EquipeResponse(EquipeCreate):
    id: UUID
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
