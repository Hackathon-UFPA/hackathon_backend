from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Integer
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class MaterialTreinamento(SQLModel, table=True):
    """Material de uma sessão do treinamento: só o link (RNF20)."""

    __tablename__ = "materiais_treinamento"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sessao_id: UUID = Field(foreign_key="sessoes_treinamento.id", nullable=False)
    titulo: str = Field(max_length=255, nullable=False)
    url: str = Field(max_length=2048, nullable=False)
    ordem: int = Field(default=0, sa_type=Integer, nullable=False)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
