from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, SmallInteger, Text
from sqlmodel import Field, SQLModel

from app.const.enums import StatusProposta, pg_enum
from app.db.defaults import AGORA_UTC


class Submissao(SQLModel, table=True):
    """Proposta da equipe (RF26); fica como rascunho até ser enviada (RF27)."""

    __tablename__ = "submissoes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False, unique=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    tema_id: UUID | None = Field(default=None, foreign_key="temas.id")
    status: StatusProposta = Field(
        default=StatusProposta.RASCUNHO,
        sa_type=pg_enum(StatusProposta, "status_proposta"),
        nullable=False,
    )
    titulo: str | None = Field(default=None)
    descricao: str | None = Field(default=None, sa_type=Text)
    # Números dos ODS atendidos (1 a 17)
    ods: list[int] | None = Field(default=None, sa_type=ARRAY(SmallInteger))
    bases_dados: str | None = Field(default=None, sa_type=Text)
    # URL externa do PDF anexo, quando exigido
    documento_url: str | None = Field(default=None)
    enviado_em: datetime | None = Field(default=None)
    criado_em: datetime | None = Field(default=None, sa_column_kwargs={"server_default": AGORA_UTC})
    # Último salvamento do rascunho
    atualizado_em: datetime | None = Field(default=None)
