from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from app.const.enums import StatusComprovante
from app.schemas.auth import validar_link_do_comprovante


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


# O que a pessoa envia ao mandar o comprovante de novo (RF21). O usuário vem do token e o
# hackathon é o das inscrições abertas, como no cadastro.
class ComprovanteEnvio(BaseModel):
    arquivo_url: Annotated[HttpUrl, AfterValidator(validar_link_do_comprovante)] = Field(
        description=(
            "Link https de um PDF ou imagem (png, jpg, jpeg) do comprovante de vínculo, já "
            "enviado pela interface a um serviço externo de armazenamento"
        ),
        examples=["https://res.cloudinary.com/.../comprovante.pdf"],
    )


class ComprovanteRecusa(BaseModel):
    motivo_recusa: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        max_length=2000, examples=["Documento ilegível"]
    )


class UsuarioResumo(BaseModel):
    """Quem enviou o comprovante, para conferir o vínculo."""

    id: UUID
    nome: str | None = None
    email: str
    instituicao: str | None = None
    curso: str | None = None
    periodo: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ComprovanteAdminResponse(ComprovanteVinculoResponse):
    usuario: UsuarioResumo
