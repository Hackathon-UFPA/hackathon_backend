from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Integer
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class Apoiador(SQLModel, table=True):
    """Realizador, apoiador ou patrocinador da edição (RF14). Link e logo, nunca arquivo."""

    __tablename__ = "apoiadores"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    nome: str = Field(max_length=255, nullable=False)
    categoria: str = Field(max_length=80, nullable=False)
    logo_url: str | None = Field(default=None, max_length=2048)
    site_url: str | None = Field(default=None, max_length=2048)
    ordem: int = Field(default=0, sa_type=Integer, nullable=False)
    publicado: bool = Field(default=False, nullable=False)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    atualizado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
