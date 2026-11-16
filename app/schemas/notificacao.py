from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import CanalNotificacao, StatusEnvioNotificacao, TipoNotificacao
from app.schemas.resultado import ParecerResponse


class ReferenciaNotificacao(BaseModel):
    tipo: str = Field(description="Tipo do objeto de origem (ex.: CONVITE, HOMOLOGACAO)")
    id: UUID


class NotificacaoGenericaResponse(BaseModel):
    """Notificação da central de qualquer tipo, exceto RESULTADO."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Igual a `notificacao_id`")
    notificacao_id: UUID = Field(description="Id na central; use-o nas rotas de leitura")
    tipo: Literal[
        TipoNotificacao.CONVITE,
        TipoNotificacao.ACEITE,
        TipoNotificacao.INSCRICAO,
        TipoNotificacao.PROPOSTA,
        TipoNotificacao.MENTOR,
        TipoNotificacao.CHAT,
        TipoNotificacao.PRAZO,
    ]
    titulo: str
    mensagem: str
    dados: dict | None = Field(
        default=None, description="Detalhes do fato, que variam por tipo (ex.: `resposta`)"
    )
    referencia: ReferenciaNotificacao | None = None
    criado_em: datetime
    lida_em: datetime | None = Field(default=None, description="Nulo enquanto não lida")


class NotificacaoResultadoResponse(BaseModel):
    """Notificação do resultado (RF33). Os campos de antes continuam com o mesmo nome e
    significado; `id` segue sendo o da linha do RF33. A única mudança do contrato é aditiva:
    `notificacao_id`, `tipo`, `titulo`, `dados`, `referencia` e `lida_em`."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Id da notificação do RF33 (inalterado)")
    notificacao_id: UUID = Field(description="Id na central; use-o nas rotas de leitura")
    tipo: Literal[TipoNotificacao.RESULTADO]
    titulo: str
    dados: dict | None = None
    referencia: ReferenciaNotificacao | None = None
    lida_em: datetime | None = Field(default=None, description="Nulo enquanto não lida")
    hackathon_id: UUID
    equipe_id: UUID
    submissao_id: UUID
    aprovada: bool
    mensagem: str
    canal: CanalNotificacao
    status_envio: StatusEnvioNotificacao = Field(
        description="PENDENTE, ENVIADO ou FALHA (com `erro`). Na plataforma nasce ENVIADO."
    )
    enviado_em: datetime | None = None
    erro: str | None = None
    criado_em: datetime
    pareceres: list[ParecerResponse] = Field(
        description="Pareceres anônimos dos avaliadores sobre a proposta da equipe"
    )


NotificacaoResponse = Annotated[
    NotificacaoResultadoResponse | NotificacaoGenericaResponse, Field(discriminator="tipo")
]


class ContagemNaoLidasResponse(BaseModel):
    nao_lidas: int


class MarcadasComoLidasResponse(BaseModel):
    marcadas: int = Field(description="Quantas estavam não lidas e foram marcadas agora")
