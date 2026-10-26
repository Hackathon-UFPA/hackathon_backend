from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.const.enums import StatusConvite


# O líder informa só nome e e-mail; o resto a pessoa completa ao confirmar (RF18, RV20)
class ConviteCreate(BaseModel):
    equipe_id: UUID
    convidado_por: UUID
    nome: str = Field(max_length=255, examples=["Maria Souza"])
    email: EmailStr = Field(examples=["maria@example.com"])


class ConviteUpdate(BaseModel):
    status: StatusConvite


# Sem o token: ele só vai no link do e-mail
class ConviteResponse(ConviteCreate):
    id: UUID
    usuario_id: UUID | None = None
    status: StatusConvite
    enviado_em: datetime | None = None
    respondido_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
