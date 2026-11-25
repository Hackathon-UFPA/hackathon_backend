from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel


class EntregaMentoria(SQLModel, table=True):
    __tablename__ = "entregas_mentoria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["marco_id", "hackathon_id"],
            ["marcos_mentoria.id", "marcos_mentoria.hackathon_id"],
            name="fk_entregas_mentoria_marco_edicao",
        ),
        ForeignKeyConstraint(
            ["equipe_id", "hackathon_id"],
            ["equipes.id", "equipes.hackathon_id"],
            name="fk_entregas_mentoria_equipe_edicao",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    marco_id: UUID = Field(nullable=False)
    equipe_id: UUID = Field(nullable=False)
    hackathon_id: UUID = Field(nullable=False)
    enviado_por: UUID = Field(foreign_key="usuarios.id", nullable=False)
    enviado_em: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    data_limite_no_envio: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    descricao: str = Field(sa_type=Text, nullable=False)
    referencias: list[str] = Field(default_factory=list, sa_type=ARRAY(Text), nullable=False)
