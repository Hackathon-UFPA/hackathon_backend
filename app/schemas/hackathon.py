from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import StatusHackathon


class HackathonCreate(BaseModel):
    nome: str | None = Field(default=None, max_length=255, examples=["Hackathon UFPA 2026"])
    tema: str | None = Field(default=None, max_length=255, examples=["Cidades inteligentes"])
    data_inicio: datetime | None = None
    data_fim: datetime | None = None
    status: StatusHackathon = Field(default=StatusHackathon.INSCRICOES)


class HackathonUpdate(BaseModel):
    nome: str | None = Field(default=None, max_length=255)
    tema: str | None = Field(default=None, max_length=255)
    data_inicio: datetime | None = None
    data_fim: datetime | None = None
    status: StatusHackathon | None = None


class HackathonResponse(HackathonCreate):
    id: UUID
    status: StatusHackathon | None = None

    model_config = ConfigDict(from_attributes=True)
