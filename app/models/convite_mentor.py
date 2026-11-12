from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class ConviteMentor(SQLModel, table=True):
    __tablename__ = "convites_mentor"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    usuario_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    # NULL apenas no histórico revogado anterior ao vínculo obrigatório com edição.
    hackathon_id: UUID | None = Field(default=None, foreign_key="hackathon.id")
    email_enfileirado: bool = Field(default=False, nullable=False)
    token_hash: str = Field(max_length=64, unique=True, nullable=False)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    expira_em: datetime
    utilizado_em: datetime | None = Field(default=None)
