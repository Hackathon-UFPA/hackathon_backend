from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AceiteTermoCreate(BaseModel):
    termo_id: UUID
    usuario_id: UUID


class AceiteTermoResponse(AceiteTermoCreate):
    id: UUID
    aceito_em: datetime

    model_config = ConfigDict(from_attributes=True)
