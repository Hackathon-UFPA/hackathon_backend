from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.const.enums import StatusEmail
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
    hackathon_id: UUID = Field(description="Edição vinculada ao primeiro convite do mentor")


class MentorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: TextoMentor | None = None
    email: EmailStr | None = None
    empresa_parceira: TextoMentor | None = None
    area_atuacao: TextoMentor | None = None
    max_equipes: CapacidadeMentor | None = None
    hackathon_id: UUID | None = Field(
        default=None, description="Obrigatório ao alterar e-mail: edição do novo convite"
    )

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
    hackathon_id: UUID = Field(
        description="Edição recebida no link; deve coincidir com a edição persistida no convite"
    )


class ConviteMentorResponse(BaseModel):
    mentor: MentorResponse
    termos: list[TermoResponse]
    senha_necessaria: bool
    hackathon_id: UUID


class ConviteMentorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hackathon_id: UUID = Field(description="Edição deste convite, inclusive para mentor já ativo")


class ConviteMentorAdminResponse(BaseModel):
    id: UUID
    hackathon_id: UUID | None
    criado_em: datetime
    expira_em: datetime
    encerrado_em: datetime | None
    email_enfileirado: bool
    status_email: StatusEmail | None
    cancelado_em: datetime | None
    pendencia_administrativa: bool = Field(
        description="Convite aberto sem e-mail enfileirado, com falha de entrega ou expirado"
    )


class MentorAtivacao(MentorPerfil, ConviteMentorRequest):
    senha: SenhaNova | None = Field(default=None, repr=False)
    termos_ids: list[UUID] = Field(min_length=2, max_length=2)


class MentorReativacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hackathon_id: UUID
