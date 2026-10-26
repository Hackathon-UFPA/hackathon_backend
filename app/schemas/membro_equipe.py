from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import FuncaoMembro


class MembroEquipeCreate(BaseModel):
    equipe_id: UUID
    usuario_id: UUID
    funcao: FuncaoMembro | None = Field(default=None, examples=["DESENVOLVEDOR"])


class MembroEquipeUpdate(BaseModel):
    funcao: FuncaoMembro | None = None


class MembroEquipeResponse(MembroEquipeCreate):
    hackathon_id: UUID
    entrou_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
