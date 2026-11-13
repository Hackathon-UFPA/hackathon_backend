from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.db.defaults import AGORA_UTC


class EventoNotificacaoMentoria(SQLModel, table=True):
    __tablename__ = "eventos_notificacao_mentoria"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    atribuicao_id: UUID = Field(foreign_key="atribuicoes_mentor.id", nullable=False)
    usuario_id: UUID = Field(foreign_key="usuarios.id", nullable=False)
    tipo: str = Field(sa_type=Text, nullable=False)
    mensagem: str = Field(sa_type=Text, nullable=False)
    criado_em: datetime | None = Field(
        default=None, nullable=False, sa_column_kwargs={"server_default": AGORA_UTC}
    )
    email_enfileirado: bool = Field(default=False, nullable=False)
    publicado_na_plataforma_em: datetime | None = Field(default=None)
