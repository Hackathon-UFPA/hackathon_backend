from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import StatusProposta
from app.schemas.tema import Ods


# Rascunho (RF27): todos os campos da proposta são opcionais até o envio
class SubmissaoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tema_id: UUID | None = None
    titulo: str | None = Field(default=None, max_length=255, examples=["App de coleta seletiva"])
    descricao: str | None = None
    ods: list[Ods] | None = Field(default=None, examples=[[11, 12]])
    bases_dados: str | None = Field(default=None, examples=["IBGE - Censo 2022"])
    documento_url: str | None = None


class SubmissaoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tema_id: UUID | None = None
    titulo: str | None = Field(default=None, max_length=255)
    descricao: str | None = None
    ods: list[Ods] | None = None
    bases_dados: str | None = None
    documento_url: str | None = None


class SubmissaoResponse(SubmissaoCreate):
    id: UUID
    equipe_id: UUID
    hackathon_id: UUID
    status: StatusProposta
    enviado_em: datetime | None = None
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
