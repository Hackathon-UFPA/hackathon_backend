from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class FaseCronograma(SQLModel, table=True):
    """Fase extra do cronograma (RF13). As datas do edital vêm da tabela `hackathon`."""

    __tablename__ = "fases_cronograma"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    nome: str = Field(max_length=255, nullable=False)
    descricao: str | None = Field(default=None, sa_type=Text)
    inicio: datetime = Field(nullable=False)
    fim: datetime = Field(nullable=False)
    publicado: bool = Field(default=False, nullable=False)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    atualizado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
