from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.const.enums import CanalNotificacao, StatusEnvioNotificacao, TipoNotificacao, pg_enum
from app.db.defaults import AGORA_UTC


class NotificacaoResultado(SQLModel, table=True):
    """Aviso do resultado a um integrante da equipe (RF33), com status de envio rastreável."""

    __tablename__ = "notificacoes_resultado"
    __table_args__ = (
        UniqueConstraint(
            "homologacao_id", "usuario_id", "canal", name="uq_notificacoes_resultado_destinatario"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    homologacao_id: UUID = Field(foreign_key="homologacoes_resultado.id", nullable=False)
    hackathon_id: UUID = Field(foreign_key="hackathon.id", nullable=False)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False)
    submissao_id: UUID = Field(foreign_key="submissoes.id", nullable=False)
    usuario_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    aprovada: bool = Field(nullable=False)
    mensagem: str = Field(sa_type=Text, nullable=False)
    canal: CanalNotificacao = Field(
        sa_type=pg_enum(CanalNotificacao, "canal_notificacao"), nullable=False
    )
    status_envio: StatusEnvioNotificacao = Field(
        sa_type=pg_enum(StatusEnvioNotificacao, "status_envio_notificacao"), nullable=False
    )
    enviado_em: datetime | None = Field(default=None)
    erro: str | None = Field(default=None, sa_type=Text)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )


class Notificacao(SQLModel, table=True):
    """Central de notificações in-app (BE-S5-04): um aviso a um destinatário. Só o próprio
    usuário a vê. `chave_idempotencia` evita o mesmo aviso duas vezes ao mesmo usuário."""

    __tablename__ = "notificacoes"
    __table_args__ = (
        UniqueConstraint("usuario_id", "chave_idempotencia", name="uq_notificacoes_usuario_chave"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    usuario_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    tipo: TipoNotificacao = Field(
        sa_type=pg_enum(TipoNotificacao, "tipo_notificacao"), nullable=False
    )
    titulo: str = Field(sa_type=Text, nullable=False)
    mensagem: str = Field(sa_type=Text, nullable=False)
    dados: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    referencia_tipo: str | None = Field(default=None, sa_type=Text)
    referencia_id: UUID | None = Field(default=None)
    chave_idempotencia: str = Field(sa_type=Text, nullable=False)
    # Só no tipo RESULTADO: a linha do RF33 (status de envio e pareceres) que originou o aviso
    notificacao_resultado_id: UUID | None = Field(
        default=None, foreign_key="notificacoes_resultado.id", unique=True
    )
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    lida_em: datetime | None = Field(default=None)
