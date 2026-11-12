from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import SmallInteger, Text
from sqlmodel import Field, SQLModel

from app.const.enums import StatusEmail, TipoEmail, pg_enum
from app.db.defaults import AGORA_UTC


class EmailOutbox(SQLModel, table=True):
    """E-mail na fila de envio (RNF28). Gravado na transação da ação que o originou."""

    __tablename__ = "emails_outbox"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tipo: TipoEmail = Field(sa_type=pg_enum(TipoEmail, "tipo_email"), nullable=False)
    destinatario_email: str = Field(sa_type=Text, nullable=False)
    destinatario_nome: str | None = Field(default=None, sa_type=Text)
    usuario_id: UUID | None = Field(default=None, foreign_key="usuarios.id")
    assunto: str = Field(sa_type=Text, nullable=False)
    corpo_texto: str | None = Field(default=None, sa_type=Text)
    corpo_html: str | None = Field(default=None, sa_type=Text)
    chave_idempotencia: str | None = Field(default=None, sa_type=Text, unique=True)
    status: StatusEmail = Field(
        default=StatusEmail.PENDENTE,
        sa_type=pg_enum(StatusEmail, "status_email"),
        nullable=False,
    )
    tentativas: int = Field(default=0, sa_type=SmallInteger, nullable=False)
    max_tentativas: int = Field(sa_type=SmallInteger, nullable=False)
    proxima_tentativa_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    reservado_ate: datetime | None = Field(default=None)
    ultimo_erro: str | None = Field(default=None, sa_type=Text)
    provedor_mensagem_id: str | None = Field(default=None, sa_type=Text)
    enviado_em: datetime | None = Field(default=None)
    cancelado_em: datetime | None = Field(default=None)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    atualizado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
