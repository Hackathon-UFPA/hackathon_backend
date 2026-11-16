"""Schemas do perfil do usuário, da recuperação de senha e da gestão administrativa (BE-S5-07).

Todos recusam campos desconhecidos (`extra="forbid"`): quem manda `papel`, `ativo` ou
`situacao_conta` onde isso não é permitido recebe 422, em vez de ter o campo ignorado em silêncio.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.const.enums import PapelUsuario
from app.schemas.auth import DESCRICAO_DA_SENHA, SenhaNova, Texto
from app.security.senha import SENHA_MAX_CARACTERES

TAMANHO_DO_TOKEN = dict(min_length=43, max_length=128)


class _SemNulos(BaseModel):
    """Campo enviado não pode ser nulo: para deixar como está, basta não enviar."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def recusar_nulos(self):
        if any(getattr(self, campo) is None for campo in self.model_fields_set):
            raise ValueError("Os campos enviados não podem ser nulos")
        return self


class PerfilUpdate(_SemNulos):
    """Dados que a própria pessoa pode alterar. Perfil, situação, e-mail e capacidade de mentoria
    ficam de fora de propósito (veja as rotas próprias de e-mail e a gestão administrativa)."""

    nome: Texto | None = None
    instituicao: Texto | None = None
    curso: Texto | None = None
    periodo: int | None = Field(default=None, gt=0)
    empresa_parceira: Texto | None = Field(default=None, description="Somente Mentor")
    area_atuacao: Texto | None = Field(default=None, description="Somente Mentor")


class TrocaEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    novo_email: EmailStr = Field(examples=["novo@ufpa.br"])
    senha: str = Field(
        min_length=1, max_length=SENHA_MAX_CARACTERES, description="Senha atual, para confirmar"
    )


class TrocaSenhaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    senha_atual: str = Field(min_length=1, max_length=SENHA_MAX_CARACTERES)
    senha_nova: SenhaNova = Field(description=DESCRICAO_DA_SENHA)


class RecuperarSenhaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(examples=["joao@ufpa.br"])


class RedefinirSenhaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(
        repr=False, description="Valor recebido no link do e-mail", **TAMANHO_DO_TOKEN
    )
    senha_nova: SenhaNova = Field(description=DESCRICAO_DA_SENHA)


class ConfirmarEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(
        repr=False, description="Valor recebido no link do e-mail", **TAMANHO_DO_TOKEN
    )


class MensagemResponse(BaseModel):
    detail: str


class SessaoResponse(BaseModel):
    """Quando a sessão atual vence (RF09): a interface usa para avisar antes de expirar."""

    expira_em: datetime
    segundos_restantes: int


class UsuarioAdminUpdate(_SemNulos):
    """Edição de um usuário por quem o gerencia (RN24). O e-mail não entra: quem troca é o
    próprio dono, com confirmação. A capacidade de mentoria fica em /admin/mentores."""

    nome: Texto | None = None
    papel: PapelUsuario | None = None
    instituicao: Texto | None = None
    curso: Texto | None = None
    periodo: int | None = Field(default=None, gt=0)
