from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, HttpUrl, StringConstraints

from app.const.enums import PapelUsuario
from app.schemas.usuario import UsuarioCreate, UsuarioResponse
from app.security.senha import SENHA_MAX_CARACTERES, SENHA_MIN_CARACTERES, validar_forca_da_senha

# O arquivo fica em um serviço externo (ex.: Cloudinary); a API guarda só o link
EXTENSOES_COMPROVANTE = (".pdf", ".png", ".jpg", ".jpeg")

DESCRICAO_DA_SENHA = (
    f"De {SENHA_MIN_CARACTERES} a {SENHA_MAX_CARACTERES} caracteres, com pelo menos uma letra "
    "e um número"
)

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]

SenhaNova = Annotated[
    str,
    Field(min_length=SENHA_MIN_CARACTERES, max_length=SENHA_MAX_CARACTERES),
    AfterValidator(validar_forca_da_senha),
]


def validar_link_do_comprovante(url: HttpUrl) -> HttpUrl:
    if url.scheme != "https":
        raise ValueError("O link do comprovante deve usar https")
    if not (url.path or "").lower().endswith(EXTENSOES_COMPROVANTE):
        raise ValueError("O comprovante deve ser um arquivo PDF ou uma imagem (png, jpg ou jpeg)")
    return url


class CadastroRequest(BaseModel):
    """Cadastro público de participante (RF01). O perfil nunca vem do cliente."""

    nome: Texto = Field(description="Nome completo", examples=["João da Silva"])
    email: EmailStr = Field(
        description="Não pode repetir, mesmo com letras maiúsculas diferentes",
        examples=["joao@ufpa.br"],
    )
    senha: SenhaNova = Field(description=DESCRICAO_DA_SENHA, examples=["segredo123"])
    instituicao: Texto = Field(examples=["UFPA"])
    curso: Texto = Field(examples=["Sistemas de Informação"])
    periodo: int = Field(gt=0, examples=[5])
    comprovante_url: Annotated[HttpUrl, AfterValidator(validar_link_do_comprovante)] = Field(
        description=(
            "Link https de um PDF ou imagem (png, jpg, jpeg) do comprovante de vínculo, já "
            "enviado pela interface a um serviço externo de armazenamento"
        ),
        examples=["https://res.cloudinary.com/.../comprovante.pdf"],
    )


class LoginRequest(BaseModel):
    email: EmailStr = Field(examples=["joao@ufpa.br"])
    # Sem regra de força: contas antigas continuam entrando, e quem erra recebe a mensagem genérica
    senha: str = Field(min_length=1, max_length=SENHA_MAX_CARACTERES, examples=["segredo123"])


class TokenResponse(BaseModel):
    access_token: str = Field(
        description="Enviar em todo pedido protegido, no cabeçalho Authorization: Bearer <token>"
    )
    token_type: str = "bearer"
    expires_in: int = Field(description="Validade do token, em segundos", examples=[3600])
    # A interface escolhe o painel pelo papel, sem precisar chamar /auth/me
    usuario: UsuarioResponse = Field(description="Dados de quem entrou, com o papel e a situação")


# Cadastro de outros perfis por quem tem permissão (RF07, RF08): o criador define a senha inicial
class UsuarioAdminCreate(UsuarioCreate):
    senha: SenhaNova = Field(
        description=f"Senha inicial definida por quem cadastra. {DESCRICAO_DA_SENHA}",
        examples=["segredo123"],
    )


class PerfisCadastraveisResponse(BaseModel):
    perfis: list[PapelUsuario] = Field(
        description="Perfis que o usuário logado pode cadastrar",
        examples=[["COMITE_TECNICO", "MENTOR"]],
    )
