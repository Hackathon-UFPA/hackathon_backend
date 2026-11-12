from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, SmallInteger, Text
from sqlmodel import Field, SQLModel


class VersaoProposta(SQLModel, table=True):
    """Cada envio definitivo da proposta, com o conteúdo enviado e o próprio protocolo
    (BE-S5-09). Imutável: o banco recusa UPDATE. A versão 1 é o envio original."""

    __tablename__ = "versoes_proposta"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    submissao_id: UUID = Field(foreign_key="submissoes.id", nullable=False)
    numero: int = Field(sa_type=SmallInteger, nullable=False)
    tema_id: UUID | None = Field(default=None, foreign_key="temas.id")
    titulo: str | None = Field(default=None)
    descricao: str | None = Field(default=None, sa_type=Text)
    ods: list[int] | None = Field(default=None, sa_type=ARRAY(SmallInteger))
    bases_dados: str | None = Field(default=None, sa_type=Text)
    documento_url: str | None = Field(default=None)
    protocolo_id: UUID = Field(foreign_key="protocolos.id", nullable=False, unique=True)
    enviada_por: UUID | None = Field(default=None, foreign_key="usuarios.id")
    enviada_em: datetime = Field(nullable=False)
