from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.const.enums import StatusComprovante, TipoIntegrante

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class AutodeclaracaoEnvio(BaseModel):
    """O que a própria pessoa declara sobre o seu vínculo (BE-S5-03). O usuário vem do token:
    ninguém declara por outra pessoa. Estudante informa instituição, curso e período; profissional,
    organização e cargo. Campos do outro tipo ou desconhecidos dão 422."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoIntegrante = Field(examples=["ESTUDANTE"])
    instituicao: Texto | None = Field(default=None, examples=["UFPA"])
    curso: Texto | None = Field(default=None, examples=["Sistemas de Informação"])
    periodo: int | None = Field(default=None, gt=0, le=32767, examples=[5])
    organizacao: Texto | None = Field(default=None, examples=["Açaí Valley"])
    cargo: Texto | None = Field(default=None, examples=["Engenheira de software"])

    @model_validator(mode="after")
    def campos_do_tipo(self):
        if self.tipo == TipoIntegrante.ESTUDANTE:
            obrigatorios, proibidos = ("instituicao", "curso", "periodo"), ("organizacao", "cargo")
        else:
            obrigatorios, proibidos = ("organizacao", "cargo"), ("instituicao", "curso", "periodo")
        faltando = [c for c in obrigatorios if getattr(self, c) is None]
        sobrando = [c for c in proibidos if getattr(self, c) is not None]
        if faltando:
            raise ValueError(f"Para o tipo {self.tipo}, informe: {', '.join(faltando)}")
        if sobrando:
            raise ValueError(f"Para o tipo {self.tipo}, não informe: {', '.join(sobrando)}")
        return self


class AutodeclaracaoResponse(BaseModel):
    id: UUID
    hackathon_id: UUID
    tipo: TipoIntegrante
    instituicao: str | None = None
    curso: str | None = None
    periodo: int | None = None
    organizacao: str | None = None
    cargo: str | None = None
    declarada_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ComprovacaoResumo(BaseModel):
    """O comprovante mais recente do vínculo que vale para a pessoa. Não traz o link do
    documento: ele é privado do dono e dos conferentes."""

    id: UUID
    tipo_vinculo: TipoIntegrante
    status: StatusComprovante
    motivo_recusa: str | None = None
    enviado_em: datetime | None = None
    validado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AutodeclaracaoSituacaoResponse(BaseModel):
    """A declaração (o que a pessoa afirma) lado a lado com a comprovação (o que foi verificado)."""

    hackathon_id: UUID
    atual: AutodeclaracaoResponse | None = Field(
        default=None, description="A declaração mais recente; vazio se a pessoa nunca declarou"
    )
    historico: list[AutodeclaracaoResponse] = Field(
        description="Todas as declarações da pessoa nesta edição, da mais recente à mais antiga"
    )
    tipo_indicado_pelo_lider: TipoIntegrante | None = Field(
        default=None, description="Tipo que o líder indicou, para quem já está em uma equipe"
    )
    comprovante: ComprovacaoResumo | None = Field(
        default=None, description="Comprovante mais recente do vínculo que vale para a pessoa"
    )
    vinculo_comprovado: bool = Field(
        description="Verdadeiro só com comprovante APROVADO: declarar não comprova nada"
    )
    autodeclaracao_exigida: bool = Field(description="A edição exige a declaração na homologação")
    comprovante_exigido: bool = Field(
        description="A edição exige comprovante aprovado para este tipo de vínculo"
    )
