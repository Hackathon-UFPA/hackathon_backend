"""
Schemas: modelos Pydantic de entrada e saída das rotas. Um arquivo por entidade.

Padrão de nomes: `<Entidade>Create` (entrada) e `<Entidade>Response` (saída,
com `model_config = ConfigDict(from_attributes=True)` para converter a partir do model).
"""
