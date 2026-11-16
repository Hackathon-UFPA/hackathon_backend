from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class SessaoTreinamento(SQLModel, table=True):
    """Sessão do treinamento, com data, horário e local ou link (RF35)."""

    __tablename__ = "sessoes_treinamento"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    titulo: str = Field(max_length=255, nullable=False)
    descricao: str | None = Field(default=None, sa_type=Text)
    inicio: datetime = Field(nullable=False)
    fim: datetime | None = Field(default=None)
    local: str | None = Field(default=None, max_length=255)
    link_url: str | None = Field(default=None, max_length=2048)
    publicado: bool = Field(default=False, nullable=False)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    atualizado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
