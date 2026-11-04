from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.const.enums import RecomendacaoAvaliacao, StatusAvaliacao


class NotaCriterio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterio_id: UUID
    nota: Decimal = Field(allow_inf_nan=False)


class AvaliacaoRascunho(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notas: list[NotaCriterio] = Field(default_factory=list)
    parecer: str | None = None
    recomendacao: RecomendacaoAvaliacao | None = None

    @model_validator(mode="after")
    def criterios_distintos(self):
        ids = [n.criterio_id for n in self.notas]
        if len(ids) != len(set(ids)):
            raise ValueError("Não repita critérios na avaliação.")
        return self


class AvaliacaoEnviar(AvaliacaoRascunho):
    """Corpo substitui o rascunho; sem corpo, envia o conteúdo já salvo."""


class AvaliacaoResultado(BaseModel):
    status: StatusAvaliacao
    nota_final: Decimal | None


class AvaliacaoResponse(AvaliacaoResultado):
    id: UUID
    submissao_id: UUID
    avaliador_id: UUID
    rubrica_id: UUID | None
    notas: list[NotaCriterio]
    parecer: str | None
    recomendacao: RecomendacaoAvaliacao | None
    atualizado_em: datetime
    avaliado_em: datetime | None
