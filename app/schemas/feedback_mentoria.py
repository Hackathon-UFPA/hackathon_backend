"""Contratos dos feedbacks do mentor (RF40) e do histórico da mentoria (RF42).

Nenhuma resposta expõe `atribuicao_id`, e-mail ou id do autor: o feedback de um mentor anterior
aparece só com o nome dele."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.conteudo import DataUtc
from app.schemas.mentoria import EntregaMentoriaResponse


class StatusAcompanhamento(StrEnum):
    """Lista provisória, ainda em validação pelo grupo. Fica no banco como varchar com CHECK
    (não é enum do PostgreSQL), por isso não está em `app/const/enums.py`."""

    NO_RITMO = "NO_RITMO"
    ATENCAO = "ATENCAO"
    EM_RISCO = "EM_RISCO"
    CONCLUIDO = "CONCLUIDO"


TextoFeedback = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class FeedbackMentoriaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: TextoFeedback = Field(examples=["Priorizem o fluxo de cadastro antes do próximo marco."])
    status_acompanhamento: StatusAcompanhamento = Field(examples=["ATENCAO"])
    marco_id: UUID | None = Field(
        default=None, description="Marco da edição a que o feedback se refere. Opcional."
    )
    entrega_id: UUID | None = Field(
        default=None,
        description="Entrega da equipe. Sem `marco_id`, o marco é o da entrega. Opcional.",
    )
    corrige_id: UUID | None = Field(
        default=None,
        description=(
            "Feedback do próprio autor, na mesma equipe, que este substitui. Cada feedback "
            "pode ser corrigido uma única vez."
        ),
    )


class FeedbackMentoriaResponse(BaseModel):
    id: UUID
    equipe_id: UUID
    hackathon_id: UUID
    marco_id: UUID | None
    entrega_id: UUID | None
    autor_nome: str | None
    status_acompanhamento: StatusAcompanhamento
    texto: str
    criado_em: DataUtc
    corrige_id: UUID | None
    corrigido_por_id: UUID | None = Field(description="Feedback que corrigiu este, se houver")


class ItemHistoricoEntrega(BaseModel):
    tipo: Literal["ENTREGA"] = "ENTREGA"
    ocorrido_em: DataUtc = Field(description="Data de envio da entrega")
    entrega: EntregaMentoriaResponse


class ItemHistoricoFeedback(BaseModel):
    tipo: Literal["FEEDBACK"] = "FEEDBACK"
    ocorrido_em: DataUtc = Field(description="Data de criação do feedback")
    feedback: FeedbackMentoriaResponse


ItemHistorico = Annotated[ItemHistoricoEntrega | ItemHistoricoFeedback, Field(discriminator="tipo")]
