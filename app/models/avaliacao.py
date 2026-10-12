from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Numeric, Text
from sqlmodel import Field, SQLModel


class Avaliacao(SQLModel, table=True):
    __tablename__ = "avaliacoes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    submissao_id: UUID = Field(foreign_key="submissoes.id", nullable=False)
    avaliador_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    nota: Decimal | None = Field(default=None, sa_type=Numeric)
    comentarios: str | None = Field(default=None, sa_type=Text)
    avaliado_em: datetime | None = Field(default=None)
