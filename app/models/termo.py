from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.const.enums import TipoTermo, pg_enum
from app.db.defaults import AGORA_UTC


class Termo(SQLModel, table=True):
    __tablename__ = "termos"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    tipo: TipoTermo = Field(sa_type=pg_enum(TipoTermo, "tipo_termo"), nullable=False)
    versao: str = Field(nullable=False)
    titulo: str = Field(nullable=False)
    # Pelo menos um dos dois: texto do documento ou URL externa
    conteudo: str | None = Field(default=None, sa_type=Text)
    url: str | None = Field(default=None)
    vigente: bool = Field(default=False, nullable=False)
    publicado_em: datetime | None = Field(
        default=None, sa_column_kwargs={"server_default": AGORA_UTC}
    )
