from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class AtribuicaoMentor(SQLModel, table=True):
    __tablename__ = "atribuicoes_mentor"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    mentor_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    atribuido_por: UUID = Field(foreign_key="usuarios.id", nullable=False)
    atribuido_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    atribuicao_anterior_id: UUID | None = Field(default=None, foreign_key="atribuicoes_mentor.id")
    motivo: str | None = Field(default=None, sa_type=Text)
    encerrada_em: datetime | None = Field(default=None)
    encerrada_por: UUID | None = Field(default=None, foreign_key="usuarios.id")
    motivo_encerramento: str | None = Field(default=None, sa_type=Text)
