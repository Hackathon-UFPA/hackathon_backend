from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import TipoMarcoMentoria
from app.schemas.conteudo import DataUtc, LinkHttps, Parcial, TextoLongo, Titulo

OrdemMarco = Annotated[int, Field(ge=0, le=2147483647, strict=True)]


class MarcoMentoriaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Titulo = Field(examples=["Protótipo navegável"])
    descricao: TextoLongo = Field(examples=["Descreva o fluxo principal e o que já funciona."])
    data_limite: DataUtc = Field(
        description="Prazo inclusivo. Datas sem fuso são interpretadas em UTC.",
        examples=["2026-12-08T23:59:00Z"],
    )
    ordem: OrdemMarco = Field(default=0, description="Desempate entre marcos com o mesmo prazo.")
    tipo: TipoMarcoMentoria = Field(
        default=TipoMarcoMentoria.PARCIAL,
        description="FINAL reserva o último marco da edição para a futura submissão final.",
    )


class MarcoMentoriaUpdate(Parcial):
    titulo: Titulo | None = None
    descricao: TextoLongo | None = None
    data_limite: DataUtc | None = Field(default=None, examples=["2026-12-09T23:59:00Z"])
    ordem: OrdemMarco | None = None
    tipo: TipoMarcoMentoria | None = None


class MarcoMentoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hackathon_id: UUID
    titulo: str
    descricao: str
    data_limite: DataUtc
    ordem: int
    tipo: TipoMarcoMentoria
    criado_em: DataUtc
    atualizado_em: DataUtc


class EntregaMentoriaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marco_id: UUID = Field(examples=["4f870fb8-5957-4bb4-8075-ca8371297c75"])
    descricao: TextoLongo = Field(examples=["Implementamos os fluxos de cadastro e consulta."])
    referencias: list[LinkHttps] = Field(
        default_factory=list,
        description="Links HTTPS externos associados ao material da entrega.",
        examples=[["https://github.com/equipe/prototipo"]],
    )


class EntregaMentoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    marco_id: UUID
    equipe_id: UUID
    hackathon_id: UUID
    enviado_por: UUID
    enviado_em: DataUtc
    data_limite_no_envio: DataUtc
    descricao: str
    referencias: list[str]
