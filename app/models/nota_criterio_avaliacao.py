from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel


class NotaCriterioAvaliacao(SQLModel, table=True):
    __tablename__ = "notas_criterio_avaliacao"
    __table_args__ = (
        UniqueConstraint("avaliacao_id", "criterio_id", name="uq_notas_avaliacao_criterio"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    avaliacao_id: UUID = Field(foreign_key="avaliacoes.id", nullable=False, ondelete="CASCADE")
    criterio_id: UUID = Field(foreign_key="criterios_rubrica.id", nullable=False)
    nota: Decimal = Field(sa_type=Numeric, nullable=False)
