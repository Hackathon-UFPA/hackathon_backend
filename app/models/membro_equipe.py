from uuid import UUID

from sqlmodel import Field, SQLModel

from app.const.enums import FuncaoMembro, pg_enum


class MembroEquipe(SQLModel, table=True):
    __tablename__ = "membros_equipe"

    equipe_id: UUID = Field(foreign_key="equipes.id", primary_key=True)
    usuario_id: UUID = Field(foreign_key="usuarios.id", primary_key=True)
    funcao: FuncaoMembro | None = Field(
        default=None, sa_type=pg_enum(FuncaoMembro, "funcao_membro")
    )
