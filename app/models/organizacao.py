from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.const.enums import TipoOrganizacao, pg_enum
from app.db.defaults import AGORA_UTC


class Organizacao(SQLModel, table=True):
    """Empresa ou instituição de ensino que organiza hackathons na plataforma."""

    __tablename__ = "organizacoes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    nome: str = Field(max_length=255, nullable=False)
    tipo: TipoOrganizacao = Field(
        sa_type=pg_enum(TipoOrganizacao, "tipo_organizacao"), nullable=False
    )
    site: str | None = Field(default=None, max_length=255)
    descricao: str | None = Field(default=None, sa_type=Text)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    atualizado_em: datetime | None = Field(default=None)
