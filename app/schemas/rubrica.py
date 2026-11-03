from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.tema import TextoObrigatorio, Titulo
from app.validations.rubrica import normalizar_nome


class CriterioRubricaIn(BaseModel):
    """Cada critério tem nome, descrição, peso (percentual) e escala de notas (RF16)."""

    nome: Titulo = Field(examples=["Inovação"])
    descricao: TextoObrigatorio = Field(examples=["Originalidade da solução proposta"])
    peso: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2, examples=["30"])
    escala_min: int = Field(ge=0, le=1000, examples=[0])
    escala_max: int = Field(ge=1, le=1000, examples=[10])

    @field_validator("peso")
    @classmethod
    def peso_com_duas_casas(cls, peso: Decimal) -> Decimal:
        # Mesmo formato do numeric(5,2): a resposta do PUT igual à das consultas
        return peso.quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def escala_crescente(self):
        if self.escala_min >= self.escala_max:
            raise ValueError("escala_min deve ser menor que escala_max")
        return self


class RubricaUpdate(BaseModel):
    """Lista completa de critérios: substitui a anterior. Pode ficar incompleta no rascunho;
    soma de 100% e critérios mínimos são exigidos só na publicação."""

    criterios: list[CriterioRubricaIn] = Field(max_length=50)

    @model_validator(mode="after")
    def nomes_unicos(self):
        nomes = [normalizar_nome(c.nome) for c in self.criterios]
        if len(nomes) != len(set(nomes)):
            raise ValueError("há critérios com o mesmo nome")
        return self


class CriterioRubricaResponse(BaseModel):
    id: UUID
    nome: str
    descricao: str
    peso: Decimal
    escala_min: int
    escala_max: int
    ordem: int

    model_config = ConfigDict(from_attributes=True)


class RubricaResponse(BaseModel):
    id: UUID
    hackathon_id: UUID
    publicada: bool
    publicada_em: datetime | None = None
    soma_pesos: Decimal
    criterios: list[CriterioRubricaResponse]


class RubricaRascunhoResponse(RubricaResponse):
    atualizado_em: datetime | None = None
    # O que ainda impede a publicação; vazio quando pronta (ou já publicada)
    pendencias: list[str]
