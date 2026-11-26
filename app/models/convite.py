from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import DateTime, SmallInteger, text
from sqlmodel import Field, SQLModel

from app.const.config import settings
from app.const.enums import StatusConvite, TipoIntegrante, pg_enum
from app.db.defaults import AGORA_UTC


class Convite(SQLModel, table=True):
    __tablename__ = "convites"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    equipe_id: UUID = Field(foreign_key="equipes.id", nullable=False)
    nome: str = Field(nullable=False)
    email: str = Field(nullable=False)
    # Preenchido quando a pessoa convidada já tem (ou cria) conta
    usuario_id: UUID | None = Field(default=None, foreign_key="usuarios.id")
    convidado_por: UUID = Field(foreign_key="usuarios.id", nullable=False)
    # Indicado pelo líder (BE-S5-01); a pessoa convidada não o altera
    tipo_integrante: TipoIntegrante = Field(
        default=TipoIntegrante.ESTUDANTE,
        sa_type=pg_enum(TipoIntegrante, "tipo_integrante"),
        nullable=False,
    )
    status: StatusConvite = Field(
        default=StatusConvite.PENDENTE,
        sa_type=pg_enum(StatusConvite, "status_convite"),
        nullable=False,
    )
    token: UUID = Field(default_factory=uuid4, unique=True, nullable=False)
    # Link de cadastro próprio (BE-S5-02), só para e-mail sem conta: guarda o SHA-256 do token
    token_hash: str | None = Field(default=None, max_length=64)
    token_expira_em: datetime | None = Field(default=None)
    token_utilizado_em: datetime | None = Field(default=None)
    enviado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    respondido_em: datetime | None = Field(default=None)
    # BE-S5-06: quantas vezes o aviso foi renovado e quando saiu o último (UTC)
    reenvios: int = Field(default=0, sa_type=SmallInteger, nullable=False)
    ultimo_envio_em: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": text("now()")},
    )

    @property
    def proximo_reenvio_em(self) -> datetime | None:
        """Quando o líder pode pedir outro reenvio. Considera só o intervalo mínimo; é `None`
        quando o limite de reenvios do convite se esgotou ou o convite não está mais pendente.
        Uma data no passado significa que já pode reenviar."""
        if self.status != StatusConvite.PENDENTE or self.reenvios >= settings.CONVITE_REENVIO_MAX:
            return None
        if self.ultimo_envio_em is None:
            return None
        ultimo = self.ultimo_envio_em
        ultimo = ultimo if ultimo.tzinfo else ultimo.replace(tzinfo=UTC)
        return ultimo + timedelta(seconds=settings.CONVITE_REENVIO_INTERVALO_SEGUNDOS)
