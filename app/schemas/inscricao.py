from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import FuncaoMembro, SituacaoEquipe, StatusComprovante, StatusConvite
from app.const.inscricao import CodigoPendencia


class PendenciaResponse(BaseModel):
    codigo: CodigoPendencia
    mensagem: str
    usuario_id: UUID | None = Field(
        default=None, description="Quem precisa resolver, quando a pendência é de uma pessoa"
    )
    bloqueia_conclusao: bool = Field(
        description="Impede o líder de concluir a inscrição. As demais só impedem a homologação"
    )


class IntegrantePainelResponse(BaseModel):
    usuario_id: UUID | None = Field(
        default=None, description="Vazio quando o convite foi para um e-mail sem conta"
    )
    nome: str | None = None
    email: str
    funcao: FuncaoMembro | None = None
    integrante: bool = Field(description="False para quem ainda não entrou: convite em aberto")
    convite: StatusConvite | None = Field(
        default=None, description="Vazio para o líder, que não foi convidado"
    )
    termos_aceitos: bool = Field(description="Aceitou as versões vigentes do regulamento e termo")
    comprovante: StatusComprovante | None = Field(
        default=None, description="Vazio quando nenhum comprovante foi enviado"
    )


class ProtocoloResponse(BaseModel):
    numero: str
    emitido_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PainelEquipeResponse(BaseModel):
    equipe_id: UUID
    hackathon_id: UUID
    nome: str | None = None
    situacao: SituacaoEquipe
    inscricao_concluida_em: datetime | None = None
    homologada_em: datetime | None = None
    protocolo: ProtocoloResponse | None = None
    minimo_integrantes: int
    maximo_integrantes: int
    total_integrantes: int
    inscricoes_abertas: bool
    voce_e_lider: bool
    pode_concluir: bool = Field(
        description="Verdadeiro só para o líder, com a equipe em formação e sem bloqueios"
    )
    integrantes: list[IntegrantePainelResponse]
    pendencias: list[PendenciaResponse]


class ConclusaoInscricaoResponse(BaseModel):
    mensagem: str
    equipe_id: UUID
    situacao: SituacaoEquipe
    inscricao_concluida_em: datetime
    homologada_em: datetime | None = None
    protocolo: ProtocoloResponse


class ReavaliacaoResponse(BaseModel):
    avaliadas: int
    homologadas: int = Field(description="Equipes que passaram a HOMOLOGADA")
    revertidas: int = Field(description="Equipes que voltaram a AGUARDANDO_HOMOLOGACAO")
