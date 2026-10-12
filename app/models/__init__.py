"""
Models: tabelas do banco com SQLModel (`table=True`). Um arquivo por tabela.

A estrutura da tabela no banco é criada pelas migrations do Flyway (pasta `migrations/`);
o model precisa refletir exatamente essa estrutura.

Exemplo (models/produto.py):

    from uuid import UUID, uuid4
    from sqlmodel import Field, SQLModel

    class Produto(SQLModel, table=True):
        __tablename__ = "produto"

        id: UUID = Field(default_factory=uuid4, primary_key=True)
        nome: str = Field(max_length=255, nullable=False)
"""

from .artefato import Artefato
from .avaliacao import Avaliacao
from .equipe import Equipe
from .hackathon import Hackathon
from .membro_equipe import MembroEquipe
from .submissao import Submissao
from .usuario import Usuario

__all__ = [
    "Artefato",
    "Avaliacao",
    "Equipe",
    "Hackathon",
    "MembroEquipe",
    "Submissao",
    "Usuario",
]
