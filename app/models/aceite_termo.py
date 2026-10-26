from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class AceiteTermo(SQLModel, table=True):
    __tablename__ = "aceites_termos"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    termo_id: UUID = Field(foreign_key="termos.id", nullable=False)
    usuario_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    aceito_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
