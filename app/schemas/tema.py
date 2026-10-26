from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Número de um ODS da ONU
Ods = Annotated[int, Field(ge=1, le=17)]


class TemaCreate(BaseModel):
    hackathon_id: UUID
    titulo: str = Field(max_length=255, examples=["Monitoramento do desmatamento"])
    descricao: str | None = None
    contexto: str | None = None
    ods: list[Ods] = Field(default_factory=list, examples=[[13, 15]])
    ativo: bool = True


class TemaUpdate(BaseModel):
    titulo: str | None = Field(default=None, max_length=255)
    descricao: str | None = None
    contexto: str | None = None
    ods: list[Ods] | None = None
    ativo: bool | None = None


class TemaResponse(TemaCreate):
    id: UUID
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
