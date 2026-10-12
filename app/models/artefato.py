from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.const.enums import CategoriaArtefato, pg_enum


class Artefato(SQLModel, table=True):
    __tablename__ = "artefatos"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False)
    nome: str = Field(nullable=False)
    categoria: CategoriaArtefato = Field(
        sa_type=pg_enum(CategoriaArtefato, "categoria_artefato"), nullable=False
    )
    # URL externa (ex: cloudinary, github)
    url: str = Field(nullable=False)
    criado_em: datetime | None = Field(default=None)
