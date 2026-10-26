from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel

from app.const.enums import FuncaoMembro, pg_enum
from app.db.defaults import AGORA_UTC


class MembroEquipe(SQLModel, table=True):
    __tablename__ = "membros_equipe"

    equipe_id: UUID = Field(foreign_key="equipes.id", primary_key=True)
    usuario_id: UUID = Field(foreign_key="usuarios.id", primary_key=True)
    # Repete o hackathon da equipe para garantir uma equipe por pessoa em cada edição (RN02)
    hackathon_id: UUID = Field(nullable=False)
    funcao: FuncaoMembro | None = Field(
        default=None, sa_type=pg_enum(FuncaoMembro, "funcao_membro")
    )
    entrou_em: datetime | None = Field(default=None, sa_column_kwargs={"server_default": AGORA_UTC})
