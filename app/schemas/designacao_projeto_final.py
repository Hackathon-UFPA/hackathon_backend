from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.schemas.designacao_avaliacao import PropostaParaAvaliacaoResponse
from app.schemas.mentoria import ArtefatosSubmissaoFinalResponse


class ConfiguracaoAvaliacaoTecnicaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    avaliadores_por_projeto_final: int = Field(ge=2, le=3, examples=[3])


class ConfiguracaoAvaliacaoTecnicaResponse(BaseModel):
    hackathon_id: UUID
    avaliadores_por_projeto_final: int | None = None


class RedistribuicaoProjetoFinalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    avaliador_ids: list[UUID] = Field(
        min_length=2,
        max_length=3,
        examples=[["3fa85f64-5717-4562-b3fc-2c963f66afa6", "7c9e6679-7425-40de-944b-e07fc1f90ae7"]],
    )


class DistribuicaoProjetosFinaisResponse(BaseModel):
    hackathon_id: UUID
    avaliadores_por_projeto_final: int
    projetos_distribuidos: int = Field(description="Projetos que receberam novas designações")
    designacoes_criadas: int
    projetos_ja_completos: int = Field(description="Projetos que já tinham avaliadores")


class AvaliadorTecnicoDesignadoResponse(BaseModel):
    id: UUID
    nome: str | None = None
    email: str
    atribuido_em: datetime | None = None


class ProjetoFinalDesignadoAdminResponse(BaseModel):
    submissao_id: UUID
    equipe_id: UUID
    titulo: str | None = None
    avaliadores: list[AvaliadorTecnicoDesignadoResponse]
    pronto_para_avaliacao: bool = Field(
        default=False, description="A proposta aprovada possui uma submissão final validada."
    )


class ProjetoFinalParaAvaliacaoResponse(PropostaParaAvaliacaoResponse):
    submissao_final: ArtefatosSubmissaoFinalResponse | None = Field(
        default=None, description="Artefatos validados do marco FINAL, quando já enviados."
    )

    @computed_field
    @property
    def pronto_para_avaliacao(self) -> bool:
        return self.submissao_final is not None


class ConflitoProjetoFinalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipe_id: UUID
    avaliador_id: UUID
    motivo: str = Field(min_length=1, max_length=2000, examples=["Orientador de um integrante"])

    @field_validator("motivo")
    @classmethod
    def motivo_nao_vazio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("Informe o motivo do conflito.")
        return valor


class ConflitoProjetoFinalResponse(BaseModel):
    id: UUID
    hackathon_id: UUID
    equipe_id: UUID
    avaliador_id: UUID
    motivo: str
    registrado_por: UUID
    registrado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
