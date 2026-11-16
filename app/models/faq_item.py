from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Integer, Text
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class FaqItem(SQLModel, table=True):
    """Pergunta frequente da edição, ordenável (RF12)."""

    __tablename__ = "faq_itens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    pergunta: str = Field(max_length=500, nullable=False)
    resposta: str = Field(sa_type=Text, nullable=False)
    ordem: int = Field(default=0, sa_type=Integer, nullable=False)
    publicado: bool = Field(default=False, nullable=False)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    atualizado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
