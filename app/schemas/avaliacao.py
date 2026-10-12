from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AvaliacaoCreate(BaseModel):
    submissao_id: UUID
    avaliador_id: UUID
    nota: Decimal | None = Field(default=None, examples=[8.5])
    comentarios: str | None = None


class AvaliacaoUpdate(BaseModel):
    nota: Decimal | None = None
    comentarios: str | None = None


class AvaliacaoResponse(AvaliacaoCreate):
    id: UUID
    avaliado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
