from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.const.enums import StatusHackathon


class HackathonCreate(BaseModel):
    nome: str | None = Field(default=None, max_length=255, examples=["Hackathon UFPA 2026"])
    tema: str | None = Field(default=None, max_length=255, examples=["Cidades inteligentes"])
    data_inicio: datetime | None = None
    data_fim: datetime | None = None
    status: StatusHackathon = Field(default=StatusHackathon.INSCRICOES)
    min_integrantes: int = Field(default=3, ge=1)
    max_integrantes: int = Field(default=5, ge=1)
    inscricoes_inicio: datetime | None = None
    inscricoes_fim: datetime | None = None
    homologacao_fim: datetime | None = None
    propostas_inicio: datetime | None = None
    propostas_fim: datetime | None = None

    @model_validator(mode="after")
    def validar_integrantes(self):
        if self.min_integrantes > self.max_integrantes:
            raise ValueError("min_integrantes não pode ser maior que max_integrantes")
        return self


class HackathonUpdate(BaseModel):
    nome: str | None = Field(default=None, max_length=255)
    tema: str | None = Field(default=None, max_length=255)
    data_inicio: datetime | None = None
    data_fim: datetime | None = None
    status: StatusHackathon | None = None
    min_integrantes: int | None = Field(default=None, ge=1)
    max_integrantes: int | None = Field(default=None, ge=1)
    inscricoes_inicio: datetime | None = None
    inscricoes_fim: datetime | None = None
    homologacao_fim: datetime | None = None
    propostas_inicio: datetime | None = None
    propostas_fim: datetime | None = None


class HackathonResponse(HackathonCreate):
    id: UUID
    status: StatusHackathon | None = None

    model_config = ConfigDict(from_attributes=True)
