from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Equipe(SQLModel, table=True):
    __tablename__ = "equipes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    nome: str | None = Field(default=None)
    criado_em: datetime | None = Field(default=None)
    atualizado_em: datetime | None = Field(default=None)
