from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.const.enums import StatusComprovante


class ComprovanteVinculoCreate(BaseModel):
    usuario_id: UUID
    hackathon_id: UUID
    arquivo_url: str = Field(examples=["https://res.cloudinary.com/.../comprovante.pdf"])


# Conferência pelo Comitê Científico (RF21)
class ComprovanteVinculoUpdate(BaseModel):
    status: StatusComprovante = Field(examples=["RECUSADO"])
    motivo_recusa: str | None = Field(default=None, examples=["Documento ilegível"])
    validado_por: UUID

    @model_validator(mode="after")
    def validar_motivo(self):
        if self.status == StatusComprovante.RECUSADO and not self.motivo_recusa:
            raise ValueError("Informe o motivo da recusa")
        return self


class ComprovanteVinculoResponse(ComprovanteVinculoCreate):
    id: UUID
    status: StatusComprovante
    motivo_recusa: str | None = None
    enviado_em: datetime | None = None
    validado_por: UUID | None = None
    validado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
