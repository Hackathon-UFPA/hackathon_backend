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
