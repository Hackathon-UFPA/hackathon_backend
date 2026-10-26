from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.const.enums import StatusComprovante, pg_enum
from app.db.defaults import AGORA_UTC


class ComprovanteVinculo(SQLModel, table=True):
    __tablename__ = "comprovantes_vinculo"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    usuario_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    # URL externa do PDF (ex: cloudinary)
    arquivo_url: str = Field(nullable=False)
    status: StatusComprovante = Field(
        default=StatusComprovante.PENDENTE,
        sa_type=pg_enum(StatusComprovante, "status_comprovante"),
        nullable=False,
    )
    motivo_recusa: str | None = Field(default=None, sa_type=Text)
    enviado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    validado_por: UUID | None = Field(default=None, foreign_key="usuarios.id")
    validado_em: datetime | None = Field(default=None)
