from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import StatusEmail, TipoEmail


class EmailResponse(BaseModel):
    """Situação de um e-mail da fila. Nunca traz o conteúdo da mensagem: ele pode ter links de
    acesso e é apagado depois do envio."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "tipo": "CONVITE_EQUIPE",
                    "destinatario_email": "maria@example.com",
                    "destinatario_nome": "Maria Souza",
                    "usuario_id": None,
                    "assunto": "Convite para participar de uma equipe no Hackathon UFPA",
                    "status": "PENDENTE",
                    "tentativas": 1,
                    "max_tentativas": 5,
                    "proxima_tentativa_em": "2026-11-12T13:30:00",
                    "ultimo_erro": "TimeoutError",
                    "enviado_em": None,
                    "criado_em": "2026-11-12T13:00:00",
                    "atualizado_em": "2026-11-12T13:00:30",
                }
            ]
        },
    )

    id: UUID
    tipo: TipoEmail
    destinatario_email: str
    destinatario_nome: str | None = None
    usuario_id: UUID | None = Field(
        default=None, description="Conta do destinatário, quando ele já tem uma"
    )
    assunto: str
    status: StatusEmail = Field(
        description=(
            "PENDENTE (na fila ou aguardando nova tentativa), ENVIANDO (reservado por um "
            "worker), ENVIADO (o provedor aceitou) ou FALHA (erro permanente ou tentativas "
            "esgotadas; só volta para a fila com o reenvio manual)"
        )
    )
    tentativas: int = Field(description="Tentativas de envio já feitas")
    max_tentativas: int
    proxima_tentativa_em: datetime = Field(
        description="Quando o worker tenta de novo (UTC). Só importa enquanto PENDENTE"
    )
    ultimo_erro: str | None = Field(
        default=None, description="Motivo da última falha do provedor, sem dados sensíveis"
    )
    enviado_em: datetime | None = Field(default=None, description="Preenchido quando ENVIADO (UTC)")
    cancelado_em: datetime | None = Field(
        default=None,
        description="Convite revogado: mensagem cancelada, sem possibilidade de reenvio",
    )
    criado_em: datetime
    atualizado_em: datetime
