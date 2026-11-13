from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.const.enums import FaseRubrica, pg_enum
from app.db.defaults import AGORA_UTC


class Rubrica(SQLModel, table=True):
    __tablename__ = "rubricas"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Uma rubrica por fase em cada edição (uq_rubricas_hackathon_fase)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    fase: FaseRubrica = Field(
        default=FaseRubrica.PROPOSTA,
        sa_type=pg_enum(FaseRubrica, "fase_rubrica"),
        nullable=False,
    )
    # Nula enquanto rascunho; preenchida, a rubrica fica imutável (RN09)
    publicada_em: datetime | None = Field(default=None)
    criado_em: datetime | None = Field(default=None, sa_column_kwargs={"server_default": AGORA_UTC})
    atualizado_em: datetime | None = Field(default=None)
