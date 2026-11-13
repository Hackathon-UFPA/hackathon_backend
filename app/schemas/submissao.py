from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import StatusProposta
from app.schemas.protocolo import ProtocoloResponse
from app.schemas.tema import Ods


# Rascunho (RF27): todos os campos da proposta são opcionais até o envio
class SubmissaoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tema_id: UUID | None = None
    titulo: str | None = Field(default=None, max_length=255, examples=["App de coleta seletiva"])
    descricao: str | None = None
    ods: list[Ods] | None = Field(default=None, examples=[[11, 12]])
    bases_dados: str | None = Field(default=None, examples=["IBGE - Censo 2022"])
    documento_url: str | None = None


class SubmissaoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tema_id: UUID | None = None
    titulo: str | None = Field(default=None, max_length=255, examples=["App de coleta seletiva"])
    descricao: str | None = Field(default=None, examples=["Aplicativo que conecta catadores"])
    ods: list[Ods] | None = Field(default=None, examples=[[11, 12]])
    bases_dados: str | None = Field(default=None, examples=["IBGE - Censo 2022"])
    documento_url: str | None = None


class SubmissaoResponse(SubmissaoCreate):
    id: UUID
    equipe_id: UUID
    hackathon_id: UUID
    status: StatusProposta
    enviado_em: datetime | None = None
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubmissaoReenvio(BaseModel):
    """Conteúdo completo da nova versão (BE-S5-09). As regras são as do envio definitivo: o
    servidor confere tema, campos obrigatórios e ODS; `documento_url` é opcional."""

    model_config = ConfigDict(extra="forbid")

    tema_id: UUID
    titulo: str = Field(max_length=255, examples=["App de coleta seletiva"])
    descricao: str = Field(examples=["Aplicativo que conecta catadores"])
    ods: list[Ods] = Field(min_length=1, examples=[[11, 12]])
    bases_dados: str = Field(examples=["IBGE - Censo 2022"])
    documento_url: str | None = None


class SubmissaoEnviadaResponse(SubmissaoResponse):
    protocolo: ProtocoloResponse
    # Número da versão enviada (1 = envio original). Nulo só em dado legado sem histórico.
    versao: int | None = None


class VersaoPropostaResponse(BaseModel):
    numero: int
    tema_id: UUID | None = None
    titulo: str | None = None
    descricao: str | None = None
    ods: list[int] | None = None
    bases_dados: str | None = None
    documento_url: str | None = None
    enviada_por: UUID | None = None
    enviada_em: datetime
    protocolo: ProtocoloResponse
