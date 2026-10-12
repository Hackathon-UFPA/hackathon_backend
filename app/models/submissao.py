from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel


class Submissao(SQLModel, table=True):
    __tablename__ = "submissoes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    titulo: str | None = Field(default=None)
    descricao: str | None = Field(default=None, sa_type=Text)
    enviado_em: datetime | None = Field(default=None)
