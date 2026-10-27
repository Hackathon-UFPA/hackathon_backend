from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variáveis de ambiente do projeto. Lidas do ambiente (docker compose) ou do arquivo .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    API_TITLE: str = "API"
    API_VERSION: str = "0.1.0"
    BASEPATH: str = ""
    CORS_ORIGINS: str = "*"

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "app_db"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"

    # Autenticação (RF02, RNF15): sem valor padrão, a API não sobe sem a chave
    JWT_SECRET: str = Field(min_length=32)
    JWT_EXPIRE_MINUTES: int = Field(default=60, gt=0)
    LOGIN_MAX_TENTATIVAS: int = Field(default=5, gt=0)
    LOGIN_BLOQUEIO_MINUTOS: int = Field(default=15, gt=0)

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origem.strip() for origem in self.CORS_ORIGINS.split(",")]


settings = Settings()
