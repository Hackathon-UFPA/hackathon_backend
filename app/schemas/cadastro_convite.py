from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl

from app.const.enums import TipoIntegrante
from app.schemas.auth import DESCRICAO_DA_SENHA, SenhaNova, Texto, validar_link_do_comprovante

TokenDoConvite = Annotated[
    str,
    Field(
        min_length=20,
        max_length=200,
        description="Token do link recebido por e-mail (fragmento `#convite=` do endereço)",
    ),
]


class ConviteCadastroConsulta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: TokenDoConvite


class ConviteCadastroConsultaResponse(BaseModel):
    """O que a página de cadastro mostra a quem abriu o link. Só dados do próprio convite."""

    email: str = Field(description="Fixo: o cadastro é feito com o e-mail que recebeu o convite")
    nome: str = Field(description="Nome que o líder indicou; a pessoa pode corrigi-lo")
    equipe_nome: str | None = None
    lider_nome: str | None = None
    tipo_integrante: TipoIntegrante
    expira_em: datetime | None = Field(default=None, description="Validade do link, em UTC")


class CadastroPorConviteRequest(BaseModel):
    """Cadastro próprio de quem foi convidado sem ter conta (BE-S5-02). O e-mail vem do convite e
    o papel é sempre Participante; a senha é da própria pessoa, nunca do líder."""

    model_config = ConfigDict(extra="forbid")

    token: TokenDoConvite
    senha: SenhaNova = Field(description=DESCRICAO_DA_SENHA, examples=["segredo123"])
    nome: Texto | None = Field(
        default=None, description="Omitido, vale o nome que o líder indicou no convite"
    )
    instituicao: Texto | None = Field(default=None, examples=["UFPA"])
    curso: Texto | None = Field(default=None, examples=["Sistemas de Informação"])
    periodo: int | None = Field(default=None, gt=0, le=32767, examples=[5])
    comprovante_url: Annotated[HttpUrl, AfterValidator(validar_link_do_comprovante)] | None = Field(
        default=None,
        description=(
            "Opcional aqui: o comprovante também pode ser enviado depois, em `POST /comprovantes`. "
            "Link https de PDF ou imagem (png, jpg, jpeg) já guardado em serviço externo"
        ),
        examples=["https://res.cloudinary.com/.../comprovante.pdf"],
    )
