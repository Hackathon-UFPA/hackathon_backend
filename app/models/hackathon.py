from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import SmallInteger
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
    # Tamanho da equipe (RN01); 3 a 5 ainda depende da Q04
    min_integrantes: int = Field(default=3, sa_type=SmallInteger, nullable=False)
    max_integrantes: int = Field(default=5, sa_type=SmallInteger, nullable=False)
    inscricoes_inicio: datetime | None = Field(default=None)
    inscricoes_fim: datetime | None = Field(default=None)
    homologacao_fim: datetime | None = Field(default=None)
    propostas_inicio: datetime | None = Field(default=None)
    propostas_fim: datetime | None = Field(default=None)
    # Avaliadores por proposta (RF29, Q07): 2 a 3; NULL até o Organizador configurar
    avaliadores_por_proposta: int | None = Field(default=None, sa_type=SmallInteger)
    treinamento_concluido_em: datetime | None = Field(default=None)
    treinamento_concluido_por: UUID | None = Field(default=None, foreign_key="usuarios.id")
