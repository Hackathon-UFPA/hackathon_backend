from app.const.config import settings

# Os testes rodam em um banco próprio (<POSTGRES_DB>_test), nunca no de desenvolvimento ou produção.
# Isto precisa acontecer antes de qualquer import de app.db.db, que cria o engine na importação.
if not settings.POSTGRES_DB.endswith("_test"):
    settings.POSTGRES_DB = f"{settings.POSTGRES_DB}_test"
