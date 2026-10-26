from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, SmallInteger, Text
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class Tema(SQLModel, table=True):
    __tablename__ = "temas"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    titulo: str = Field(nullable=False)
    descricao: str | None = Field(default=None, sa_type=Text)
    contexto: str | None = Field(default=None, sa_type=Text)
    # Números dos ODS relacionados (1 a 17)
    ods: list[int] = Field(default_factory=list, sa_type=ARRAY(SmallInteger), nullable=False)
    ativo: bool = Field(default=True, nullable=False)
    criado_em: datetime | None = Field(default=None, sa_column_kwargs={"server_default": AGORA_UTC})
    atualizado_em: datetime | None = Field(default=None)
