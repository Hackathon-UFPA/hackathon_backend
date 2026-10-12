from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.const.enums import StatusHackathon, pg_enum


class Hackathon(SQLModel, table=True):
    __tablename__ = "hackathon"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    nome: str | None = Field(default=None)
    tema: str | None = Field(default=None)
    data_inicio: datetime | None = Field(default=None)
    data_fim: datetime | None = Field(default=None)
    status: StatusHackathon | None = Field(
        default=StatusHackathon.INSCRICOES,
        sa_type=pg_enum(StatusHackathon, "status_hackathon"),
    )
