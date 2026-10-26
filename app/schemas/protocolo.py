from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import TipoProtocolo


# Protocolo não é editado: o número e a data vêm do banco
class ProtocoloCreate(BaseModel):
    tipo: TipoProtocolo = Field(examples=["PROPOSTA"])
    equipe_id: UUID
    submissao_id: UUID | None = None
    emitido_por: UUID | None = None


class ProtocoloResponse(ProtocoloCreate):
    id: UUID
    numero: str = Field(examples=["HK2026-000001"])
    emitido_em: datetime

    model_config = ConfigDict(from_attributes=True)
