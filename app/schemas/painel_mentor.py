"""Contratos do painel do mentor (RF41). Só expõem o necessário ao acompanhamento: sem notas,
pareceres, classificação, e-mails ou ids de usuários."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.const.enums import (
    CategoriaEquipe,
    FuncaoMembro,
    StatusHackathon,
    TipoMarcoMentoria,
)
from app.schemas.conteudo import DataUtc


class SituacaoMarcoEquipe(StrEnum):
    """Andamento de uma equipe em um marco. É calculado na consulta e não existe no banco, por
    isso não fica em `app/const/enums.py`, que espelha os tipos do PostgreSQL."""

    ENTREGUE = "ENTREGUE"
    PENDENTE = "PENDENTE"  # ainda dá para enviar
    NAO_ENTREGUE = "NAO_ENTREGUE"  # prazo vencido ou edição encerrada sem registro


class ProgressoMarcos(BaseModel):
    """Contagem dos marcos parciais. O marco final fica fora: o envio dele tem fluxo próprio."""

    total: int
    entregues: int
    pendentes: int = Field(description="Sem entrega, mas ainda dentro do prazo")
    nao_entregues: int = Field(description="Prazo vencido ou edição encerrada sem entrega")


class ResumoPainel(ProgressoMarcos):
    equipes_com_nao_entregues: int


class ProximoMarco(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    titulo: str
    data_limite: DataUtc


class EquipeNoPainel(BaseModel):
    equipe_id: UUID
    equipe_nome: str | None
    categoria: CategoriaEquipe
    hackathon_id: UUID
    hackathon_nome: str | None
    hackathon_status: StatusHackathon | None
    atribuicao_id: UUID
    atribuido_em: DataUtc
    progresso: ProgressoMarcos
    proximo_marco: ProximoMarco | None = Field(
        description="Marco parcial pendente com o prazo mais próximo"
    )


class PainelMentorResponse(BaseModel):
    total: int = Field(description="Equipes que atendem aos filtros, antes da paginação")
    limite: int
    deslocamento: int
    resumo: ResumoPainel = Field(
        description="Soma de todas as equipes filtradas, não só as da página"
    )
    equipes: list[EquipeNoPainel]


class IntegranteNoPainel(BaseModel):
    nome: str | None
    funcao: FuncaoMembro | None


class EntregaNoPainel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    enviado_em: DataUtc
    data_limite_no_envio: DataUtc
    descricao: str
    referencias: list[str]


class MarcoNoPainel(BaseModel):
    id: UUID
    titulo: str
    descricao: str
    data_limite: DataUtc
    ordem: int
    tipo: TipoMarcoMentoria
    situacao: SituacaoMarcoEquipe | None = Field(
        description="Nulo no marco final ainda sem entrega, que o painel não acompanha"
    )
    entrega: EntregaNoPainel | None


class DetalheEquipeNoPainel(EquipeNoPainel):
    integrantes: list[IntegranteNoPainel]
    marcos: list[MarcoNoPainel] = Field(description="Calendário completo da edição, por prazo")
