from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class FeedbackMentoria(SQLModel, table=True):
    """Feedback imutável do mentor (RF40). O banco recusa UPDATE e DELETE: corrigir é criar outro
    registro com `corrige_id`."""

    __tablename__ = "feedbacks_mentoria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["equipe_id", "hackathon_id"],
            ["equipes.id", "equipes.hackathon_id"],
            name="fk_feedbacks_mentoria_equipe_edicao",
        ),
        ForeignKeyConstraint(
            ["marco_id", "hackathon_id"],
            ["marcos_mentoria.id", "marcos_mentoria.hackathon_id"],
            name="fk_feedbacks_mentoria_marco_edicao",
        ),
        ForeignKeyConstraint(
            ["entrega_id", "marco_id", "equipe_id", "hackathon_id"],
            [
                "entregas_mentoria.id",
                "entregas_mentoria.marco_id",
                "entregas_mentoria.equipe_id",
                "entregas_mentoria.hackathon_id",
            ],
            name="fk_feedbacks_mentoria_entrega",
        ),
        UniqueConstraint("id", "equipe_id", "autor_id", name="uq_feedbacks_mentoria_original"),
        ForeignKeyConstraint(
            ["corrige_id", "equipe_id", "autor_id"],
            [
                "feedbacks_mentoria.id",
                "feedbacks_mentoria.equipe_id",
                "feedbacks_mentoria.autor_id",
            ],
            name="fk_feedbacks_mentoria_corrige",
        ),
        UniqueConstraint(
            "autor_id", "chave_idempotencia", name="uq_feedbacks_mentoria_autor_chave"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    equipe_id: UUID = Field(nullable=False)
    hackathon_id: UUID = Field(nullable=False)
    atribuicao_id: UUID = Field(foreign_key="atribuicoes_mentor.id", nullable=False)
    autor_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    marco_id: UUID | None = Field(default=None)
    entrega_id: UUID | None = Field(default=None)
    status_acompanhamento: str = Field(max_length=20, nullable=False)
    texto: str = Field(sa_type=Text, nullable=False)
    corrige_id: UUID | None = Field(default=None)
    criado_em: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    chave_idempotencia: str | None = Field(default=None, max_length=128)
