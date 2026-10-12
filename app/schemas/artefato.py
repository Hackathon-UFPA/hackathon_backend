from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import CategoriaArtefato


class ArtefatoCreate(BaseModel):
    equipe_id: UUID
    nome: str = Field(max_length=255, examples=["Repositório do backend"])
    categoria: CategoriaArtefato = Field(examples=["REPOSITORIO_CODIGO"])
    url: str = Field(examples=["https://github.com/org/repo"])


class ArtefatoUpdate(BaseModel):
    nome: str | None = Field(default=None, max_length=255)
    categoria: CategoriaArtefato | None = None
    url: str | None = None


class ArtefatoResponse(ArtefatoCreate):
    id: UUID
    criado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
