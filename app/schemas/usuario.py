from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.const.enums import PapelUsuario


class UsuarioCreate(BaseModel):
    nome: str | None = Field(default=None, max_length=255, examples=["Joao Da Silva"])
    email: EmailStr = Field(examples=["user@example.com"])
    papel: PapelUsuario = Field(examples=["PARTICIPANTE"])
    instituicao: str | None = Field(default=None, max_length=255, examples=["UFPA"])
    curso: str | None = Field(default=None, max_length=255, examples=["Sistemas de Informação"])
    periodo: int | None = Field(default=None, gt=0, examples=[5])
    # Perfil Mentor (RF37)
    empresa_parceira: str | None = Field(default=None, max_length=255, examples=["Açaí Valley"])
    area_atuacao: str | None = Field(default=None, max_length=255, examples=["Ciência de dados"])
    max_equipes: int | None = Field(default=None, gt=0, examples=[2])


class UsuarioUpdate(BaseModel):
    nome: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    papel: PapelUsuario | None = None
    instituicao: str | None = Field(default=None, max_length=255)
    curso: str | None = Field(default=None, max_length=255)
    periodo: int | None = Field(default=None, gt=0)
    empresa_parceira: str | None = Field(default=None, max_length=255)
    area_atuacao: str | None = Field(default=None, max_length=255)
    max_equipes: int | None = Field(default=None, gt=0)
    # Desativação pelo Organizador (RF07)
    ativo: bool | None = None


class UsuarioResponse(UsuarioCreate):
    id: UUID
    ativo: bool
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
