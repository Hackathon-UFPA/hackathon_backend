from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import SmallInteger
from sqlmodel import Field, SQLModel

from app.const.enums import TipoIntegrante, pg_enum
from app.db.defaults import AGORA_UTC


class AutodeclaracaoVinculo(SQLModel, table=True):
    """O que a própria pessoa declara sobre o seu vínculo (BE-S5-03). Só recebe linhas novas:
    corrigir é declarar de novo. Não prova nada; a comprovação é o comprovante aprovado."""

    __tablename__ = "autodeclaracoes_vinculo"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    usuario_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    tipo: TipoIntegrante = Field(sa_type=pg_enum(TipoIntegrante, "tipo_integrante"), nullable=False)
    instituicao: str | None = Field(default=None)
    curso: str | None = Field(default=None)
    periodo: int | None = Field(default=None, sa_type=SmallInteger)
    organizacao: str | None = Field(default=None)
    cargo: str | None = Field(default=None)
    declarada_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
