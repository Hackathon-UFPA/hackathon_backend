from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Numeric, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.const.enums import RecomendacaoAvaliacao, StatusAvaliacao, pg_enum
from app.db.defaults import AGORA_UTC


class Avaliacao(SQLModel, table=True):
    __tablename__ = "avaliacoes"
    __table_args__ = (
        UniqueConstraint("submissao_id", "avaliador_id", name="uq_avaliacoes_submissao_avaliador"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    submissao_id: UUID = Field(foreign_key="submissoes.id", nullable=False)
    avaliador_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    nota: Decimal | None = Field(default=None, sa_type=Numeric)
    comentarios: str | None = Field(default=None, sa_type=Text)
    avaliado_em: datetime | None = Field(default=None)
    rubrica_id: UUID | None = Field(default=None, foreign_key="rubricas.id")
    status: StatusAvaliacao = Field(
        default=StatusAvaliacao.RASCUNHO,
        sa_type=pg_enum(StatusAvaliacao, "status_avaliacao"),
        nullable=False,
    )
    recomendacao: RecomendacaoAvaliacao | None = Field(
        default=None, sa_type=pg_enum(RecomendacaoAvaliacao, "recomendacao_avaliacao")
    )
    atualizado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
