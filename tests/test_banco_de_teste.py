from app.const.config import settings
from app.db.db import async_engine


def test_testes_usam_um_banco_proprio(client):
    """Trava de segurança: se isto falhar, os testes estão rodando em outro banco."""
    assert settings.POSTGRES_DB.endswith("_test")
    assert settings.DATABASE_URL.endswith("_test")


def test_a_api_e_os_testes_falam_com_o_mesmo_banco(client, sql):
    banco_da_api = client.get("/health").json()["database"]
    banco_dos_testes = sql("SELECT current_database() AS nome")[0]["nome"]

    assert banco_da_api == "ok"
    assert banco_dos_testes == settings.POSTGRES_DB
    assert async_engine.url.database == settings.POSTGRES_DB
