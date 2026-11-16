"""Schemas do conteúdo institucional da edição (BE-S5-12): apoiadores, FAQ, cronograma,
regulamento e treinamento. Links seguem a política de `app/validations/links.py` (RNF20)."""

from datetime import UTC, datetime
from typing import Annotated, ClassVar
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.const.enums import StatusHackathon, TipoTermo
from app.validations.inscricao import como_utc
from app.validations.links import validar_link_de_imagem, validar_link_https

Titulo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Categoria = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Pergunta = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
TextoLongo = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)
]
Versao = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
LinkHttps = Annotated[str, AfterValidator(validar_link_https)]
LinkImagem = Annotated[str, AfterValidator(validar_link_de_imagem)]


def _em_utc(momento: datetime) -> datetime:
    """As colunas são `timestamp` em UTC: data sem fuso vale como UTC; as demais são convertidas."""
    return como_utc(momento).astimezone(UTC)


DataUtc = Annotated[datetime, AfterValidator(_em_utc)]


class Parcial(BaseModel):
    """Atualização parcial: só muda o que foi enviado. Campo desconhecido dá 422, e `null` só
    é aceito nos campos de `NULAVEIS` (os que podem ser limpos)."""

    model_config = ConfigDict(extra="forbid")
    NULAVEIS: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def recusar_nulos(self):
        for campo in self.model_fields_set - self.NULAVEIS:
            if getattr(self, campo) is None:
                raise ValueError(f"O campo {campo} não pode ser nulo")
        return self


# --- Apoiadores (RF14) ---


class ApoiadorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: Titulo = Field(examples=["Açaí Valley"])
    categoria: Categoria = Field(
        description="Agrupa os apoiadores na página pública", examples=["Patrocinador"]
    )
    logo_url: LinkImagem | None = Field(default=None, examples=["https://cdn.exemplo.com/logo.png"])
    site_url: LinkHttps | None = Field(default=None, examples=["https://exemplo.com"])
    publicado: bool = False


class ApoiadorUpdate(Parcial):
    NULAVEIS = frozenset({"logo_url", "site_url"})

    nome: Titulo | None = None
    categoria: Categoria | None = None
    logo_url: LinkImagem | None = None
    site_url: LinkHttps | None = None
    ordem: int | None = Field(default=None, ge=0)
    publicado: bool | None = None


class ApoiadorResponse(BaseModel):
    id: UUID
    hackathon_id: UUID
    nome: str
    categoria: str
    logo_url: str | None
    site_url: str | None
    ordem: int
    publicado: bool
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ApoiadorPublico(BaseModel):
    nome: str
    logo_url: str | None
    site_url: str | None

    model_config = ConfigDict(from_attributes=True)


class ApoiadoresPorCategoria(BaseModel):
    categoria: str
    apoiadores: list[ApoiadorPublico]


# --- FAQ (RF12) ---


class FaqCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pergunta: Pergunta = Field(examples=["Quem pode participar?"])
    resposta: TextoLongo = Field(examples=["Estudantes de graduação e pós-graduação da UFPA."])
    publicado: bool = False


class FaqUpdate(Parcial):
    pergunta: Pergunta | None = None
    resposta: TextoLongo | None = None
    publicado: bool | None = None


class FaqOrdem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[UUID] = Field(
        min_length=1,
        description="Todos os ids das perguntas da edição, na nova ordem, sem repetir",
    )

    @model_validator(mode="after")
    def sem_repeticao(self):
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Há ids repetidos")
        return self


class FaqResponse(BaseModel):
    id: UUID
    hackathon_id: UUID
    pergunta: str
    resposta: str
    ordem: int
    publicado: bool
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class FaqPublico(BaseModel):
    id: UUID
    pergunta: str
    resposta: str

    model_config = ConfigDict(from_attributes=True)


# --- Cronograma (RF13, RF59) ---


class FaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: Titulo = Field(examples=["Treinamento das equipes"])
    descricao: TextoLongo | None = None
    inicio: DataUtc
    fim: DataUtc
    publicado: bool = False

    @model_validator(mode="after")
    def validar_periodo(self):
        if self.fim < self.inicio:
            raise ValueError("fim não pode ser antes de inicio")
        return self


class FaseUpdate(Parcial):
    NULAVEIS = frozenset({"descricao"})

    nome: Titulo | None = None
    descricao: TextoLongo | None = None
    inicio: DataUtc | None = None
    fim: DataUtc | None = None
    publicado: bool | None = None


class FaseCronogramaResponse(BaseModel):
    """Uma linha do cronograma. `origem` é `EDITAL` para as datas do próprio edital (inscrições,
    homologação, propostas e evento, vindas de `hackathon`, sem `id`) e `PERSONALIZADA` para as
    fases cadastradas aqui."""

    id: UUID | None = None
    origem: str
    nome: str
    descricao: str | None = None
    inicio: datetime
    fim: datetime
    publicado: bool = True
    situacao: str = Field(description="NAO_INICIADA, EM_ANDAMENTO ou ENCERRADA")
    atual: bool = Field(description="Fase em andamento agora, para destacar na linha do tempo")


# --- Regulamento e termos (RF11) ---


class TermoRascunhoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoTermo = Field(default=TipoTermo.REGULAMENTO, examples=["REGULAMENTO"])
    versao: Versao = Field(examples=["2.0"])
    titulo: Titulo = Field(examples=["Regulamento do Hackathon 2026"])
    conteudo: TextoLongo | None = Field(default=None, description="Texto do documento")
    url: LinkHttps | None = Field(default=None, description="Link https do PDF, em vez do texto")

    @model_validator(mode="after")
    def exigir_documento(self):
        if self.conteudo is None and self.url is None:
            raise ValueError("Informe o conteudo ou a url do documento")
        return self


class TermoRascunhoUpdate(Parcial):
    """Só rascunhos mudam. A versão e o tipo não mudam: uma versão publicada é imutável."""

    NULAVEIS = frozenset({"conteudo", "url"})

    titulo: Titulo | None = None
    conteudo: TextoLongo | None = None
    url: LinkHttps | None = None


class TermoAdminResponse(BaseModel):
    id: UUID
    hackathon_id: UUID
    tipo: TipoTermo
    versao: str
    titulo: str
    conteudo: str | None
    url: str | None
    vigente: bool
    rascunho: bool
    publicado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RegulamentoPublico(BaseModel):
    """Só a versão publicada aparece; `publicado_em` é a data da última atualização (RF11)."""

    id: UUID
    versao: str
    titulo: str
    conteudo: str | None
    url: str | None
    publicado_em: datetime | None

    model_config = ConfigDict(from_attributes=True)


# --- Treinamento (RF35) ---


class MaterialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Titulo = Field(examples=["Slides da sessão 1"])
    url: LinkHttps = Field(examples=["https://drive.exemplo.com/slides"])


class MaterialResponse(BaseModel):
    id: UUID
    titulo: str
    url: str
    ordem: int

    model_config = ConfigDict(from_attributes=True)


class SessaoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Titulo = Field(examples=["Introdução ao desafio"])
    descricao: TextoLongo | None = None
    inicio: DataUtc
    fim: DataUtc | None = None
    local: Titulo | None = Field(default=None, examples=["Auditório do ICEN"])
    link_url: LinkHttps | None = Field(default=None, description="Link da sala virtual")
    publicado: bool = False

    @model_validator(mode="after")
    def validar(self):
        if self.fim is not None and self.fim < self.inicio:
            raise ValueError("fim não pode ser antes de inicio")
        if self.local is None and self.link_url is None:
            raise ValueError("Informe o local ou o link da sessão")
        return self


class SessaoUpdate(Parcial):
    NULAVEIS = frozenset({"descricao", "fim", "local", "link_url"})

    titulo: Titulo | None = None
    descricao: TextoLongo | None = None
    inicio: DataUtc | None = None
    fim: DataUtc | None = None
    local: Titulo | None = None
    link_url: LinkHttps | None = None
    publicado: bool | None = None


class SessaoResponse(BaseModel):
    id: UUID
    hackathon_id: UUID
    titulo: str
    descricao: str | None
    inicio: datetime
    fim: datetime | None
    local: str | None
    link_url: str | None
    publicado: bool
    materiais: list[MaterialResponse] = []
    atualizado_em: datetime | None = None


# --- Página pública (RF10) ---


class HackathonPublico(BaseModel):
    id: UUID
    nome: str | None
    tema: str | None
    descricao: str | None
    status: StatusHackathon | None
    data_inicio: datetime | None
    data_fim: datetime | None
    inscricoes_inicio: datetime | None
    inscricoes_fim: datetime | None
    homologacao_fim: datetime | None
    propostas_inicio: datetime | None
    propostas_fim: datetime | None
    inscricoes_abertas: bool = Field(
        description="RN06: a interface mostra o botão de inscrição só quando for verdadeiro"
    )


class PaginaPublicaResponse(HackathonPublico):
    regulamento: RegulamentoPublico | None = None
    faq: list[FaqPublico] = []
    cronograma: list[FaseCronogramaResponse] = []
    apoiadores: list[ApoiadoresPorCategoria] = []
