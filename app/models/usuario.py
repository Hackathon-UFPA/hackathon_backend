from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.const.enums import PapelUsuario, pg_enum


class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    nome: str | None = Field(default=None)
    email: str = Field(unique=True, nullable=False)
    papel: PapelUsuario = Field(sa_type=pg_enum(PapelUsuario, "papel_usuario"), nullable=False)
    criado_em: datetime | None = Field(default=None)
    atualizado_em: datetime | None = Field(default=None)
