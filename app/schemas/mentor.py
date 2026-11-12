from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.schemas.auth import SenhaNova
from app.schemas.termo import TermoResponse
from app.schemas.usuario import UsuarioResponse

TextoMentor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
CapacidadeMentor = Annotated[int, Field(strict=True, gt=0, le=32767)]


class MentorPerfil(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: TextoMentor
    empresa_parceira: TextoMentor
    area_atuacao: TextoMentor


class MentorCreate(MentorPerfil):
    email: EmailStr
    max_equipes: CapacidadeMentor


class MentorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: TextoMentor | None = None
    email: EmailStr | None = None
    empresa_parceira: TextoMentor | None = None
    area_atuacao: TextoMentor | None = None
    max_equipes: CapacidadeMentor | None = None

    @model_validator(mode="after")
    def recusar_nulos(self):
        if any(getattr(self, campo) is None for campo in self.model_fields_set):
            raise ValueError("Os campos enviados não podem ser nulos")
        return self


class MentorResponse(UsuarioResponse):
    mentor_perfil_concluido_em: datetime | None
    mentor_ativado_em: datetime | None


class ConviteMentorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=43, max_length=128, repr=False)
    hackathon_id: UUID


class ConviteMentorResponse(BaseModel):
    mentor: MentorResponse
    termos: list[TermoResponse]
    senha_necessaria: bool


class MentorAtivacao(MentorPerfil, ConviteMentorRequest):
    senha: SenhaNova | None = Field(default=None, repr=False)
    termos_ids: list[UUID] = Field(min_length=2, max_length=2)


class MentorReativacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hackathon_id: UUID
