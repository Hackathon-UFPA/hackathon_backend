from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.const.enums import StatusHackathon


class HackathonCreate(BaseModel):
    nome: str | None = Field(default=None, max_length=255, examples=["Hackathon UFPA 2026"])
    tema: str | None = Field(default=None, max_length=255, examples=["Cidades inteligentes"])
    descricao: str | None = Field(
        default=None, max_length=20000, description="Texto de apresentação da página pública"
    )
    local: str | None = Field(default=None, max_length=255, examples=["Belém, PA ou On-line"])
    data_inicio: datetime | None = None
    data_fim: datetime | None = None
    status: StatusHackathon = Field(default=StatusHackathon.INSCRICOES)
    min_integrantes: int = Field(default=3, ge=1)
    max_integrantes: int = Field(default=5, ge=1)
    inscricoes_inicio: datetime | None = None
    inscricoes_fim: datetime | None = None
    homologacao_fim: datetime | None = None
    propostas_inicio: datetime | None = None
    propostas_fim: datetime | None = None
    avaliadores_por_proposta: int | None = Field(default=None, ge=2, le=3)
    # Categorias de equipe aceitas na edição (política provisória, BE-S5-01); ao menos uma
    aceita_equipe_estudantes: bool = True
    aceita_equipe_profissionais: bool = True
    aceita_equipe_mista: bool = True
    # Verificação do vínculo na homologação (política provisória, BE-S5-03)
    exige_autodeclaracao: bool = False
    exige_comprovante_estudante: bool = True
    exige_comprovante_profissional: bool = True

    @model_validator(mode="after")
    def validar_integrantes(self):
        if self.min_integrantes > self.max_integrantes:
            raise ValueError("min_integrantes não pode ser maior que max_integrantes")
        if not (
            self.aceita_equipe_estudantes
            or self.aceita_equipe_profissionais
            or self.aceita_equipe_mista
        ):
            raise ValueError("A edição precisa aceitar ao menos uma categoria de equipe")
        return self


class HackathonUpdate(BaseModel):
    """Altera apenas os campos enviados. As datas e o tamanho da equipe são validados junto
    com os valores já gravados."""

    nome: str | None = Field(default=None, max_length=255)
    tema: str | None = Field(default=None, max_length=255)
    descricao: str | None = Field(default=None, max_length=20000)
    local: str | None = Field(default=None, max_length=255)
    data_inicio: datetime | None = None
    data_fim: datetime | None = None
    status: StatusHackathon | None = None
    min_integrantes: int | None = Field(default=None, ge=1)
    max_integrantes: int | None = Field(default=None, ge=1)
    inscricoes_inicio: datetime | None = None
    inscricoes_fim: datetime | None = None
    homologacao_fim: datetime | None = None
    propostas_inicio: datetime | None = None
    propostas_fim: datetime | None = None
    avaliadores_por_proposta: int | None = Field(default=None, ge=2, le=3)
    aceita_equipe_estudantes: bool | None = None
    aceita_equipe_profissionais: bool | None = None
    aceita_equipe_mista: bool | None = None
    exige_autodeclaracao: bool | None = None
    exige_comprovante_estudante: bool | None = None
    exige_comprovante_profissional: bool | None = None

    @field_validator(
        "status",
        "min_integrantes",
        "max_integrantes",
        "aceita_equipe_estudantes",
        "aceita_equipe_profissionais",
        "aceita_equipe_mista",
        "exige_autodeclaracao",
        "exige_comprovante_estudante",
        "exige_comprovante_profissional",
        mode="before",
    )
    @classmethod
    def obrigatorio_nao_aceita_null(cls, valor):
        if valor is None:
            raise ValueError("este campo não pode ser nulo")
        return valor


class HackathonResponse(HackathonCreate):
    id: UUID
    status: StatusHackathon | None = None
    organizacao_id: UUID | None = Field(default=None, description="Organização dona da edição")
    organizacao_nome: str | None = None

    model_config = ConfigDict(from_attributes=True)
