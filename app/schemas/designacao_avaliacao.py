from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.tema import Ods


class ConfiguracaoAvaliacaoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    avaliadores_por_proposta: int = Field(ge=2, le=3, examples=[3])


class ConfiguracaoAvaliacaoResponse(BaseModel):
    hackathon_id: UUID
    avaliadores_por_proposta: int | None = None


class RedistribuicaoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    avaliador_ids: list[UUID] = Field(min_length=2, max_length=3)


class DistribuicaoResponse(BaseModel):
    hackathon_id: UUID
    avaliadores_por_proposta: int
    propostas_distribuidas: int = Field(description="Propostas que receberam novas designações")
    designacoes_criadas: int
    propostas_ja_completas: int = Field(description="Propostas que já tinham avaliadores")


class AvaliadorDesignadoResponse(BaseModel):
    id: UUID
    nome: str | None = None
    email: str
    atribuido_em: datetime | None = None


class PropostaDesignadaAdminResponse(BaseModel):
    submissao_id: UUID
    equipe_id: UUID
    titulo: str | None = None
    avaliadores: list[AvaliadorDesignadoResponse]


class PropostaParaAvaliacaoResponse(BaseModel):
    """Proposta como o avaliador a vê. Não traz a equipe (nem os integrantes)."""

    id: UUID
    hackathon_id: UUID
    tema_id: UUID | None = None
    titulo: str | None = None
    descricao: str | None = None
    ods: list[Ods] | None = None
    bases_dados: str | None = None
    documento_url: str | None = None
    enviado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
