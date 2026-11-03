from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AceiteTermoCreate(BaseModel):
    termo_id: UUID
    usuario_id: UUID


class AceiteTermoResponse(AceiteTermoCreate):
    id: UUID
    aceito_em: datetime

    model_config = ConfigDict(from_attributes=True)


# Ids das versões de termo aceitas, como listadas em /hackathons/{id}/termos/vigentes
class AceiteTermosCreate(BaseModel):
    termos_ids: list[UUID] = Field(
        min_length=1,
        examples=[["3fa85f64-5717-4562-b3fc-2c963f66afa6", "7c9e6679-7425-40de-944b-e07fc1f90ae7"]],
    )
