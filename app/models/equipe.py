from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.const.enums import SituacaoEquipe, pg_enum


class Equipe(SQLModel, table=True):
    __tablename__ = "equipes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    nome: str | None = Field(default=None)
    situacao: SituacaoEquipe = Field(
        default=SituacaoEquipe.EM_FORMACAO,
        sa_type=pg_enum(SituacaoEquipe, "situacao_equipe"),
        nullable=False,
    )
    inscricao_concluida_em: datetime | None = Field(default=None)
    homologada_em: datetime | None = Field(default=None)
    criado_em: datetime | None = Field(default=None)
    atualizado_em: datetime | None = Field(default=None)
