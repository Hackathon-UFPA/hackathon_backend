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


# O que o líder envia: a equipe vem da rota e quem convida, do token
class ConviteEnvio(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nome: str = Field(min_length=1, max_length=255, examples=["Maria Souza"])
    email: EmailStr = Field(examples=["maria@example.com"])


# Ids das versões de termo que a pessoa leu e aceita (GET /hackathons/{id}/termos/vigentes)
class ConviteAceite(BaseModel):
    termos_ids: list[UUID] = Field(min_length=1)


# Convite visto por quem recebe (RF19: aparece no painel)
class ConviteRecebidoResponse(BaseModel):
    id: UUID
    equipe_id: UUID
    equipe_nome: str | None = None
    hackathon_id: UUID
    nome: str
    status: StatusConvite
    enviado_em: datetime | None = None
