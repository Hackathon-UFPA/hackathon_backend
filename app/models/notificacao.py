from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.const.enums import CanalNotificacao, StatusEnvioNotificacao, pg_enum
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
