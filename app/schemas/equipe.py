from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.const.enums import CategoriaEquipe, SituacaoEquipe, TipoIntegrante

# Teto de convidados por pedido: barra listas absurdas antes de qualquer consulta; o limite de
# verdade é hackathon.max_integrantes (RN01, Q04).
MAX_INTEGRANTES_POR_PEDIDO = 20


class IntegranteIndicado(BaseModel):
    """O que o líder indica sobre cada integrante (BE-S5-01). Só nome, e-mail e tipo: dados
    pessoais, aceite de termos e comprovante são da própria pessoa e nunca vêm por aqui (RN05,
    RN25); campos extras dão 422."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nome: str = Field(min_length=1, max_length=255, examples=["Maria Souza"])
    email: EmailStr = Field(examples=["maria@example.com"])
    tipo_integrante: TipoIntegrante | None = Field(
        default=None,
        description=(
            "ESTUDANTE ou PROFISSIONAL. Opcional nas categorias ESTUDANTES e PROFISSIONAIS "
            "(vale o tipo da categoria); obrigatório na MISTA"
        ),
    )


class EquipeBase(BaseModel):
    hackathon_id: UUID
    nome: str | None = Field(default=None, max_length=255, examples=["Equipe Backend"])


class EquipeCreate(EquipeBase):
    model_config = ConfigDict(extra="forbid")

    categoria: CategoriaEquipe | None = Field(
        default=None,
        description="Omitida, vale ESTUDANTES (comportamento anterior à decisão de 05/11)",
    )
    tipo_lider: TipoIntegrante | None = Field(
        default=None,
        description="Tipo do próprio líder. Opcional, exceto na categoria MISTA",
    )
    integrantes: list[IntegranteIndicado] | None = Field(
        default=None,
        max_length=MAX_INTEGRANTES_POR_PEDIDO,
        description=(
            "Composição completa, sem o líder. Quando enviada, o total (líder + integrantes) "
            "precisa respeitar o mínimo e o máximo da edição e os convites saem na mesma "
            "operação. Omitida, só o líder é criado, como antes"
        ),
    )


class EquipeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(default=None, max_length=255, examples=["Equipe Backend"])


class ComposicaoUpdate(BaseModel):
    """Substitui a composição inteira da equipe (RF24): quem não está na lista é retirado."""

    model_config = ConfigDict(extra="forbid")

    categoria: CategoriaEquipe
    tipo_lider: TipoIntegrante | None = Field(
        default=None, description="Omitido, o líder mantém o tipo que já tem"
    )
    integrantes: list[IntegranteIndicado] = Field(max_length=MAX_INTEGRANTES_POR_PEDIDO)


class EquipeResponse(EquipeBase):
    id: UUID
    categoria: CategoriaEquipe
    # Controlada pelo sistema (RF22, RF23), não pelo cliente
    situacao: SituacaoEquipe
    inscricao_concluida_em: datetime | None = None
    homologada_em: datetime | None = None
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
