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

from .aceite_termo import AceiteTermo
from .artefato import Artefato
from .avaliacao import Avaliacao
from .comprovante_vinculo import ComprovanteVinculo
from .convite import Convite
from .equipe import Equipe
from .hackathon import Hackathon
from .membro_equipe import MembroEquipe
from .protocolo import Protocolo
from .submissao import Submissao
from .tema import Tema
from .termo import Termo
from .usuario import Usuario

__all__ = [
    "AceiteTermo",
    "Artefato",
    "Avaliacao",
    "ComprovanteVinculo",
    "Convite",
    "Equipe",
    "Hackathon",
    "MembroEquipe",
    "Protocolo",
    "Submissao",
    "Tema",
    "Termo",
    "Usuario",
]
