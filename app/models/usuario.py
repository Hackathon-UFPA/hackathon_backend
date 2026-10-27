from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import SmallInteger
from sqlmodel import Field, SQLModel

from app.const.enums import PapelUsuario, SituacaoConta, pg_enum


class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    nome: str | None = Field(default=None)
    email: str = Field(unique=True, nullable=False)
    papel: PapelUsuario = Field(sa_type=pg_enum(PapelUsuario, "papel_usuario"), nullable=False)
    instituicao: str | None = Field(default=None)
    curso: str | None = Field(default=None)
    periodo: int | None = Field(default=None, sa_type=SmallInteger)
    ativo: bool = Field(default=True, nullable=False)
    # Autenticação (RF01, RF02): a senha nunca é guardada, só o hash
    senha_hash: str | None = Field(default=None)
    tentativas_login: int = Field(default=0, sa_type=SmallInteger, nullable=False)
    bloqueado_ate: datetime | None = Field(default=None)
    # PENDENTE até o comprovante de vínculo ser aprovado (RN25)
    situacao_conta: SituacaoConta = Field(
        default=SituacaoConta.ATIVA,
        sa_type=pg_enum(SituacaoConta, "situacao_conta"),
        nullable=False,
    )
    # Perfil Mentor (RF37)
    empresa_parceira: str | None = Field(default=None)
    area_atuacao: str | None = Field(default=None)
    max_equipes: int | None = Field(default=None, sa_type=SmallInteger)
    criado_em: datetime | None = Field(default=None)
    atualizado_em: datetime | None = Field(default=None)
