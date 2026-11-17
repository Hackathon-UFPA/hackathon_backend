from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.const.enums import CategoriaEquipe, SituacaoEquipe, pg_enum


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
    # Indicada pelo líder (BE-S5-01); equipes anteriores à decisão de 05/11 são ESTUDANTES
    categoria: CategoriaEquipe = Field(
        default=CategoriaEquipe.ESTUDANTES,
        sa_type=pg_enum(CategoriaEquipe, "categoria_equipe"),
        nullable=False,
    )
    # BE-S5-02: quem criou e a chave que torna o POST /equipes idempotente
    criada_por: UUID | None = Field(default=None, foreign_key="usuarios.id")
    chave_idempotencia: str | None = Field(default=None, max_length=128)
    hash_requisicao: str | None = Field(default=None, max_length=64)
    inscricao_concluida_em: datetime | None = Field(default=None)
    homologada_em: datetime | None = Field(default=None)
    criado_em: datetime | None = Field(default=None)
    atualizado_em: datetime | None = Field(default=None)
