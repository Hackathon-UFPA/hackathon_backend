from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Numeric, SmallInteger, Text
from sqlmodel import Field, SQLModel


class CriterioRubrica(SQLModel, table=True):
    __tablename__ = "criterios_rubrica"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    rubrica_id: UUID = Field(foreign_key="rubricas.id", nullable=False)
    nome: str = Field(nullable=False)
    descricao: str = Field(sa_type=Text, nullable=False)
    # Percentual do critério na nota final; a soma de 100% é conferida na publicação
    peso: Decimal = Field(sa_type=Numeric(5, 2), nullable=False)
    escala_min: int = Field(sa_type=SmallInteger, nullable=False)
    escala_max: int = Field(sa_type=SmallInteger, nullable=False)
    ordem: int = Field(sa_type=SmallInteger, nullable=False)
