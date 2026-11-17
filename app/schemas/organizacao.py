from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.const.enums import TipoOrganizacao


class OrganizacaoResponse(BaseModel):
    id: UUID
    nome: str
    tipo: TipoOrganizacao
    site: str | None = None
    descricao: str | None = None
    criado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OrganizacaoUpdate(BaseModel):
    """Altera apenas os campos enviados."""

    nome: str | None = Field(default=None, min_length=1, max_length=255)
    tipo: TipoOrganizacao | None = None
    site: HttpUrl | None = None
    descricao: str | None = Field(default=None, max_length=2000)
