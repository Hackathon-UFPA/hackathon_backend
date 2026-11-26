from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKeyConstraint, Text
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class DesignacaoProjetoFinal(SQLModel, table=True):
    """Projeto final designado a um avaliador do Comitê Técnico (RF47, RF48).

    Nunca é apagada: a redistribuição preenche `removida_em`/`removida_por` (auditoria).
    A unicidade (projeto, avaliador) vale só entre as vigentes (índice parcial no banco)."""

    __tablename__ = "designacoes_projeto_final"
    __table_args__ = (
        ForeignKeyConstraint(
            ["submissao_id", "equipe_id", "hackathon_id"],
            ["submissoes.id", "submissoes.equipe_id", "submissoes.hackathon_id"],
            name="fk_designacoes_projeto_final_submissao_equipe_edicao",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    submissao_id: UUID = Field(nullable=False)
    equipe_id: UUID = Field(nullable=False)
    hackathon_id: UUID = Field(nullable=False)
    avaliador_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    atribuido_por: UUID | None = Field(default=None, foreign_key="usuarios.id")
    atribuido_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    removida_em: datetime | None = Field(default=None)
    removida_por: UUID | None = Field(default=None, foreign_key="usuarios.id")


class ConflitoProjetoFinal(SQLModel, table=True):
    """Conflito de interesse declarado entre um avaliador e uma equipe (RN13)."""

    __tablename__ = "conflitos_projeto_final"
    __table_args__ = (
        ForeignKeyConstraint(
            ["equipe_id", "hackathon_id"],
            ["equipes.id", "equipes.hackathon_id"],
            name="fk_conflitos_projeto_final_equipe_edicao",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(nullable=False)
    equipe_id: UUID = Field(nullable=False)
    avaliador_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    motivo: str = Field(sa_type=Text, nullable=False)
    registrado_por: UUID = Field(foreign_key="usuarios.id", nullable=False)
    registrado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
