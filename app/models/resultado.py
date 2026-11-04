from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Numeric, SmallInteger, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class HomologacaoResultado(SQLModel, table=True):
    """Homologação do resultado da avaliação científica (RF31). Uma por hackathon, imutável."""

    __tablename__ = "homologacoes_resultado"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False, unique=True)
    homologado_por: UUID = Field(foreign_key="usuarios.id", nullable=False)
    homologado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    total_propostas: int = Field(nullable=False)
    total_aprovadas: int = Field(nullable=False)


class ResultadoProposta(SQLModel, table=True):
    """Retrato do resultado de uma proposta no momento da homologação (RF31, RF32)."""

    __tablename__ = "resultados_proposta"
    __table_args__ = (
        UniqueConstraint(
            "homologacao_id", "classificacao", name="uq_resultados_proposta_classificacao"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    homologacao_id: UUID = Field(foreign_key="homologacoes_resultado.id", nullable=False)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    submissao_id: UUID = Field(foreign_key="submissoes.id", nullable=False, unique=True)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False)
    equipe_nome: str | None = Field(default=None, sa_type=Text)
    tema_titulo: str | None = Field(default=None, sa_type=Text)
    titulo: str | None = Field(default=None, sa_type=Text)
    nota_media: Decimal = Field(sa_type=Numeric(5, 2), nullable=False)
    classificacao: int = Field(nullable=False)
    avaliacoes: int = Field(sa_type=SmallInteger, nullable=False)
    recomendacoes_aprovacao: int = Field(sa_type=SmallInteger, nullable=False)
    recomendacoes_reprovacao: int = Field(sa_type=SmallInteger, nullable=False)
    aprovada: bool = Field(nullable=False)
