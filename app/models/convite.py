from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.const.enums import StatusConvite, pg_enum
from app.db.defaults import AGORA_UTC


class Convite(SQLModel, table=True):
    __tablename__ = "convites"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False)
    nome: str = Field(nullable=False)
    email: str = Field(nullable=False)
    # Preenchido quando a pessoa convidada já tem (ou cria) conta
    usuario_id: UUID | None = Field(default=None, foreign_key="usuarios.id")
    convidado_por: UUID = Field(foreign_key="usuarios.id", nullable=False)
    status: StatusConvite = Field(
        default=StatusConvite.PENDENTE,
        sa_type=pg_enum(StatusConvite, "status_convite"),
        nullable=False,
    )
    token: UUID = Field(default_factory=uuid4, unique=True, nullable=False)
    enviado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    respondido_em: datetime | None = Field(default=None)
