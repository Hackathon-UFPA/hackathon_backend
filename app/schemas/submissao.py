from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubmissaoCreate(BaseModel):
    equipe_id: UUID
    hackathon_id: UUID
    titulo: str | None = Field(default=None, max_length=255, examples=["App de coleta seletiva"])
    descricao: str | None = None


class SubmissaoUpdate(BaseModel):
    titulo: str | None = Field(default=None, max_length=255)
    descricao: str | None = None


class SubmissaoResponse(SubmissaoCreate):
    id: UUID
    enviado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
