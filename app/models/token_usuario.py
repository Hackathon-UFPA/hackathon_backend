from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.const.enums import FinalidadeToken, pg_enum
from app.db.defaults import AGORA_UTC


class TokenUsuario(SQLModel, table=True):
    """Token de uso único enviado por e-mail (BE-S5-07). Só o hash é guardado."""

    __tablename__ = "tokens_usuario"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    usuario_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    finalidade: FinalidadeToken = Field(
        sa_type=pg_enum(FinalidadeToken, "finalidade_token"), nullable=False
    )
    token_hash: str = Field(max_length=64, unique=True, nullable=False)
    email: str | None = Field(default=None, max_length=255)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    expira_em: datetime
    utilizado_em: datetime | None = Field(default=None)
