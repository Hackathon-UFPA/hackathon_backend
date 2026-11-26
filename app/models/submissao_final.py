from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from app.const.enums import TipoMarcoMentoria, pg_enum


class SubmissaoFinal(SQLModel, table=True):
    """Artefatos do primeiro envio, vinculados à identidade da entrega de mentoria."""

    __tablename__ = "submissoes_finais"
    __table_args__ = (
        ForeignKeyConstraint(
            ["entrega_id", "marco_id", "equipe_id", "hackathon_id"],
            [
                "entregas_mentoria.id",
                "entregas_mentoria.marco_id",
                "entregas_mentoria.equipe_id",
                "entregas_mentoria.hackathon_id",
            ],
            name="fk_submissoes_finais_entrega",
        ),
        ForeignKeyConstraint(
            ["marco_id", "hackathon_id", "tipo_marco"],
            ["marcos_mentoria.id", "marcos_mentoria.hackathon_id", "marcos_mentoria.tipo"],
            name="fk_submissoes_finais_marco_final",
        ),
        ForeignKeyConstraint(
            ["submissao_id", "equipe_id", "hackathon_id"],
            ["submissoes.id", "submissoes.equipe_id", "submissoes.hackathon_id"],
            name="fk_submissoes_finais_proposta",
        ),
        UniqueConstraint("submissao_id", name="uq_submissoes_finais_proposta"),
        CheckConstraint("tipo_marco = 'FINAL'", name="ck_submissoes_finais_marco_final"),
        CheckConstraint(
            "relatorio_tamanho_bytes BETWEEN 1 AND 10485760", name="ck_submissoes_finais_tamanho"
        ),
    )

    entrega_id: UUID = Field(primary_key=True)
    marco_id: UUID = Field(nullable=False)
    equipe_id: UUID = Field(nullable=False, index=True)
    hackathon_id: UUID = Field(nullable=False)
    submissao_id: UUID = Field(nullable=False)
    tipo_marco: TipoMarcoMentoria = Field(
        default=TipoMarcoMentoria.FINAL,
        sa_type=pg_enum(TipoMarcoMentoria, "tipo_marco_mentoria"),
        nullable=False,
    )
    repositorio_url: str = Field(max_length=2048, nullable=False)
    repositorio_validado_em: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    relatorio_pdf: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    relatorio_tamanho_bytes: int | None = Field(
        default=None,
        sa_column=Column(Integer, Computed("octet_length(relatorio_pdf)"), nullable=False),
    )
