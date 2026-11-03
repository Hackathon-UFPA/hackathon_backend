from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# Número de um ODS da ONU
Ods = Annotated[int, Field(ge=1, le=17)]

TextoObrigatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Titulo = Annotated[TextoObrigatorio, StringConstraints(max_length=255)]


class TemaCreate(BaseModel):
    """O tema tem título, descrição e pelo menos um ODS (RF15). A edição vem da rota."""

    titulo: Titulo = Field(examples=["Monitoramento do desmatamento"])
    descricao: TextoObrigatorio = Field(examples=["Soluções para acompanhar a perda de floresta"])
    contexto: str | None = None
    ods: list[Ods] = Field(min_length=1, examples=[[13, 15]])
    ativo: bool = True

    @field_validator("ods")
    @classmethod
    def ods_sem_repeticao(cls, ods: list[int]) -> list[int]:
        return sorted(set(ods))


class TemaUpdate(BaseModel):
    """Altera apenas os campos enviados. `ativo` ativa ou desativa o tema (RF15)."""

    titulo: Titulo | None = None
    descricao: TextoObrigatorio | None = None
    contexto: str | None = None
    ods: list[Ods] | None = Field(default=None, min_length=1)
    ativo: bool | None = None

    @field_validator("titulo", "descricao", "ods", "ativo", mode="before")
    @classmethod
    def obrigatorio_nao_aceita_null(cls, valor):
        if valor is None:
            raise ValueError("este campo não pode ser nulo")
        return valor

    @field_validator("ods")
    @classmethod
    def ods_sem_repeticao(cls, ods: list[int] | None) -> list[int] | None:
        return sorted(set(ods)) if ods is not None else None


class TemaResponse(BaseModel):
    id: UUID
    hackathon_id: UUID
    titulo: str
    descricao: str | None = None
    contexto: str | None = None
    ods: list[int]
    ativo: bool
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
