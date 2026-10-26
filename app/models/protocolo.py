from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import FetchedValue
from sqlmodel import Field, SQLModel

from app.const.enums import TipoProtocolo, pg_enum
from app.db.defaults import AGORA_UTC


class Protocolo(SQLModel, table=True):
    __tablename__ = "protocolos"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Gerado pelo banco (ex: HK2026-000001); não enviar no insert
    numero: str | None = Field(
        default=None,
        unique=True,
        nullable=False,
        sa_column_kwargs={"server_default": FetchedValue()},
    )
    tipo: TipoProtocolo = Field(sa_type=pg_enum(TipoProtocolo, "tipo_protocolo"), nullable=False)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False)
    submissao_id: UUID | None = Field(default=None, foreign_key="submissoes.id")
    emitido_por: UUID | None = Field(default=None, foreign_key="usuarios.id")
    emitido_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
