from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.resultado import CodigoPendenciaResultado


class HomologacaoCreate(BaseModel):
    """Decisão do Organizador: quais propostas ficam aprovadas (as demais, reprovadas)."""

    model_config = ConfigDict(extra="forbid")

    propostas_aprovadas: list[UUID] = Field(
        description=(
            "Ids das propostas (submissao_id) aprovadas. Todas precisam ser propostas "
            "ENVIADA deste hackathon, sem repetidos. Lista vazia reprova todas."
        ),
        examples=[["3fa85f64-5717-4562-b3fc-2c963f66afa6"]],
    )


class PendenciaResultadoResponse(BaseModel):
    codigo: CodigoPendenciaResultado
    mensagem: str
    submissao_id: UUID | None = None


class ResultadoPropostaResponse(BaseModel):
    submissao_id: UUID
    equipe_id: UUID
    equipe_nome: str | None = None
    tema_titulo: str | None = None
    titulo: str | None = None
    avaliadores_designados: int = Field(description="Avaliadores designados à proposta")
    avaliacoes_enviadas: int = Field(description="Avaliações definitivas (ENVIADA)")
    nota_media: Decimal | None = Field(
        default=None,
        description="Média das notas finais enviadas, duas casas (HALF_UP); null sem avaliação",
    )
    classificacao: int | None = Field(
        default=None, description="Posição pela nota média; null enquanto não houver nota"
    )
    recomendacoes_aprovacao: int
    recomendacoes_reprovacao: int
    aprovada: bool | None = Field(
        default=None, description="Decisão da homologação; null enquanto não homologado"
    )


class ResultadoAvaliacaoResponse(BaseModel):
    hackathon_id: UUID
    avaliadores_por_proposta: int | None = None
    homologado: bool
    homologado_em: datetime | None = None
    homologado_por: UUID | None = None
    homologado_por_nome: str | None = None
    pode_homologar: bool = Field(description="Verdadeiro quando não há pendências e não homologado")
    pendencias: list[PendenciaResultadoResponse]
    total_propostas: int
    total_aprovadas: int | None = None
    propostas: list[ResultadoPropostaResponse]


class PropostaAprovadaResponse(BaseModel):
    """O que é divulgado ao público (RF32): equipe, tema e título. Sem notas."""

    submissao_id: UUID
    equipe: str | None = None
    tema: str | None = None
    titulo: str | None = None


class PropostasAprovadasResponse(BaseModel):
    hackathon_id: UUID
    hackathon_nome: str | None = None
    divulgado: bool = Field(description="Falso enquanto o resultado não for homologado")
    divulgado_em: datetime | None = None
    propostas: list[PropostaAprovadaResponse]
