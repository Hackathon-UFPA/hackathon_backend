from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    MENTOR_CONVITE_MINUTOS: int = Field(default=1440, gt=0)

    # E-mail transacional (RNF28, RF60). As credenciais vêm só do ambiente.
    # `console` só registra no log (desenvolvimento); `smtp` envia de verdade.
    EMAIL_PROVIDER: Literal["console", "smtp"] = "console"
    EMAIL_REMETENTE_NOME: str = "Hackathon UFPA"
    EMAIL_REMETENTE_ENDERECO: str = "nao-responder@hackathon.local"
    SMTP_HOST: str = ""
    SMTP_PORT: int = Field(default=587, gt=0)
    SMTP_USUARIO: str = ""
    SMTP_SENHA: SecretStr = SecretStr("")
    # starttls (porta 587), ssl (porta 465) ou nenhuma (só para servidor local de testes)
    SMTP_SEGURANCA: Literal["starttls", "ssl", "nenhuma"] = "starttls"
    SMTP_TIMEOUT_SEGUNDOS: int = Field(default=30, gt=0)
    # Endereço do front: os e-mails trazem só um aviso e o link para a plataforma (RNF28)
    FRONTEND_URL: str = "http://localhost:4200"
    # Fila de envio: o worker busca os e-mails pendentes a cada EMAIL_INTERVALO_SEGUNDOS
    EMAIL_WORKER_ATIVO: bool = True
    EMAIL_INTERVALO_SEGUNDOS: int = Field(default=15, gt=0)
    EMAIL_LOTE: int = Field(default=20, gt=0)
    EMAIL_MAX_TENTATIVAS: int = Field(default=5, gt=0)
    # Espera antes da tentativa N+1: base * 2^(N-1), limitada ao máximo
    EMAIL_BACKOFF_BASE_SEGUNDOS: int = Field(default=30, gt=0)
    EMAIL_BACKOFF_MAX_SEGUNDOS: int = Field(default=1800, gt=0)
    # Um e-mail reservado e não concluído (worker caiu) volta para a fila depois deste prazo
    EMAIL_RESERVA_SEGUNDOS: int = Field(default=300, gt=0)

    @model_validator(mode="after")
    def smtp_configurado(self):
        if self.EMAIL_PROVIDER == "smtp" and not (self.SMTP_HOST and self.EMAIL_REMETENTE_ENDERECO):
            raise ValueError("EMAIL_PROVIDER=smtp exige SMTP_HOST e EMAIL_REMETENTE_ENDERECO")
        return self

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
