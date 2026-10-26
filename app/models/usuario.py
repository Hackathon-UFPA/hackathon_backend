from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import SmallInteger
from sqlmodel import Field, SQLModel

from app.const.enums import PapelUsuario, pg_enum


class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    nome: str | None = Field(default=None)
    email: str = Field(unique=True, nullable=False)
    papel: PapelUsuario = Field(sa_type=pg_enum(PapelUsuario, "papel_usuario"), nullable=False)
    instituicao: str | None = Field(default=None)
    curso: str | None = Field(default=None)
    periodo: int | None = Field(default=None, sa_type=SmallInteger)
    ativo: bool = Field(default=True, nullable=False)
    # Perfil Mentor (RF37)
    empresa_parceira: str | None = Field(default=None)
    area_atuacao: str | None = Field(default=None)
    max_equipes: int | None = Field(default=None, sa_type=SmallInteger)
    criado_em: datetime | None = Field(default=None)
    atualizado_em: datetime | None = Field(default=None)
