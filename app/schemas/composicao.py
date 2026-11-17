from uuid import UUID

from pydantic import BaseModel, Field

from app.const.enums import (
    CategoriaEquipe,
    FuncaoMembro,
    StatusComprovante,
    StatusConvite,
    TipoIntegrante,
)
from app.schemas.inscricao import PendenciaResponse


class IndicadoPeloLider(BaseModel):
    """Dado informado pelo líder. Não é verificado: a pessoa o confirma na própria conta."""

    nome: str | None = None
    email: str
    tipo_integrante: TipoIntegrante
    funcao: FuncaoMembro | None = None


class ConfirmadoPeloIntegrante(BaseModel):
    """O que a própria pessoa já fez, com a conta dela. Ninguém confirma nada por outra."""

    integrante: bool = Field(description="False enquanto o convite não foi aceito")
    usuario_id: UUID | None = Field(
        default=None, description="Só de quem já é integrante; vazio para convites em aberto"
    )
    convite: StatusConvite | None = Field(
        default=None, description="Vazio para o líder, que não foi convidado"
    )
    conta_ativa: bool | None = Field(default=None, description="Vazio para quem ainda não entrou")
    termos_aceitos: bool = Field(description="Aceitou as versões vigentes do regulamento e termo")
    comprovante: StatusComprovante | None = Field(
        default=None, description="Vazio quando nenhum comprovante foi enviado"
    )
    tipo_declarado: TipoIntegrante | None = Field(
        default=None,
        description="Tipo que a própria pessoa autodeclarou (BE-S5-03); vazio se nunca declarou",
    )
    vinculo_comprovado: bool = Field(
        default=False,
        description="Comprovante do vínculo aplicável APROVADO; a autodeclaração não conta",
    )


class IntegranteComposicaoResponse(BaseModel):
    indicado_pelo_lider: IndicadoPeloLider
    confirmado_pelo_integrante: ConfirmadoPeloIntegrante
    pendencias: list[PendenciaResponse] = Field(
        description="O que falta para esta pessoa especificamente"
    )


class ComposicaoResponse(BaseModel):
    equipe_id: UUID
    categoria: CategoriaEquipe
    minimo_integrantes: int
    maximo_integrantes: int
    total_integrantes: int = Field(description="Quem já entrou, o líder inclusive")
    total_indicados: int = Field(description="Integrantes mais convites ainda em aberto")
    integrantes: list[IntegranteComposicaoResponse]
    pendencias_da_equipe: list[PendenciaResponse] = Field(
        description="Pendências que não são de uma pessoa só (tamanho, categoria, termos)"
    )
