from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AtribuicaoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mentor_id: UUID
    motivo: Motivo | None = None


class AtribuicaoSubstituir(AtribuicaoCreate):
    atribuicao_atual_id: UUID = Field(description="Controle de concorrência: vínculo a substituir")
    motivo: Motivo


class AtribuicaoEncerrar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atribuicao_atual_id: UUID
    motivo: Motivo


class AtribuicaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    equipe_id: UUID
    hackathon_id: UUID
    mentor_id: UUID
    atribuido_por: UUID
    atribuido_em: datetime
    atribuicao_anterior_id: UUID | None
    motivo: str | None
    encerrada_em: datetime | None
    encerrada_por: UUID | None
    motivo_encerramento: str | None


class MentorContato(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str | None
    email: EmailStr
    empresa_parceira: str | None
    area_atuacao: str | None
    ativo: bool


class MentorDaEquipeResponse(BaseModel):
    atribuicao_id: UUID
    equipe_id: UUID
    hackathon_id: UUID
    atribuido_em: datetime
    mentor: MentorContato


class EquipeAcompanhadaResponse(BaseModel):
    atribuicao: AtribuicaoResponse
    equipe_nome: str | None


class TreinamentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    treinamento_concluido_em: datetime | None
    treinamento_concluido_por: UUID | None
