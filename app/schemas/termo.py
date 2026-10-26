from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.const.enums import TipoTermo


class TermoCreate(BaseModel):
    hackathon_id: UUID
    tipo: TipoTermo = Field(examples=["REGULAMENTO"])
    versao: str = Field(max_length=50, examples=["1.0"])
    titulo: str = Field(max_length=255, examples=["Regulamento do Hackathon 2026"])
    conteudo: str | None = None
    url: str | None = None
    vigente: bool = False

    @model_validator(mode="after")
    def validar_documento(self):
        if self.conteudo is None and self.url is None:
            raise ValueError("Informe o conteudo ou a url do documento")
        return self


# A versão não muda: uma alteração no texto vira uma versão nova
class TermoUpdate(BaseModel):
    titulo: str | None = Field(default=None, max_length=255)
    conteudo: str | None = None
    url: str | None = None
    vigente: bool | None = None


class TermoResponse(TermoCreate):
    id: UUID
    publicado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
