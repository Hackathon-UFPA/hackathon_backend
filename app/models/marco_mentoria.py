from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel

from app.const.enums import TipoMarcoMentoria, pg_enum


class MarcoMentoria(SQLModel, table=True):
    __tablename__ = "marcos_mentoria"
    __table_args__ = (
        UniqueConstraint("id", "hackathon_id", "tipo", name="uq_marcos_mentoria_id_edicao_tipo"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    titulo: str = Field(max_length=255, nullable=False)
    descricao: str = Field(sa_type=Text, nullable=False)
    data_limite: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    ordem: int = Field(default=0, nullable=False)
    tipo: TipoMarcoMentoria = Field(
        default=TipoMarcoMentoria.PARCIAL,
        sa_type=pg_enum(TipoMarcoMentoria, "tipo_marco_mentoria"),
        nullable=False,
    )
    criado_em: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    atualizado_em: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
