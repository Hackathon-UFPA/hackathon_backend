from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class DesignacaoAvaliacao(SQLModel, table=True):
    """Proposta designada a um avaliador (RF29). A nota é registrada em `avaliacoes`."""

    __tablename__ = "designacoes_avaliacao"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    submissao_id: UUID = Field(foreign_key="submissoes.id", nullable=False)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    avaliador_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    atribuido_por: UUID | None = Field(default=None, foreign_key="usuarios.id")
    atribuido_em: datetime | None = Field(
        default=None, sa_column_kwargs={"server_default": AGORA_UTC}
    )
