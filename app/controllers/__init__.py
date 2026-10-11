"""
Controllers: acesso ao banco de dados. Um arquivo por entidade.

Recebem a sessão (`db: AsyncSession`) e fazem as operações:
`get_<entidade>_by_id`, `criar_<entidade>`, `atualizar_<entidade>`, `deletar_<entidade>`.
Usam os helpers de `app/exceptions/db.py` para erros (404, violação de constraint)
e `app/utils/generic_db_operations.py` para atualizar instâncias.
"""
