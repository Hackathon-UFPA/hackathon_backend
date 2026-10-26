from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, HttpUrl, StringConstraints

from app.schemas.usuario import UsuarioCreate
from app.security.senha import SENHA_MAX_CARACTERES, SENHA_MIN_CARACTERES, validar_forca_da_senha

# O arquivo fica em um serviço externo (ex.: Cloudinary); a API guarda só o link
EXTENSOES_COMPROVANTE = (".pdf", ".png", ".jpg", ".jpeg")

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

    nome: Texto = Field(examples=["João da Silva"])
    email: EmailStr = Field(examples=["joao@ufpa.br"])
    senha: SenhaNova = Field(examples=["segredo123"])
    instituicao: Texto = Field(examples=["UFPA"])
    curso: Texto = Field(examples=["Sistemas de Informação"])
    periodo: int = Field(gt=0, examples=[5])
    comprovante_url: Annotated[HttpUrl, AfterValidator(validar_link_do_comprovante)] = Field(
        examples=["https://res.cloudinary.com/.../comprovante.pdf"]
    )


class LoginRequest(BaseModel):
    email: EmailStr = Field(examples=["joao@ufpa.br"])
    # Sem regra de força: contas antigas continuam entrando, e quem erra recebe a mensagem genérica
    senha: str = Field(min_length=1, max_length=SENHA_MAX_CARACTERES)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Validade em segundos
    expires_in: int


# Cadastro de outros perfis por quem tem permissão (RF07, RF08): o criador define a senha inicial
class UsuarioAdminCreate(UsuarioCreate):
    senha: SenhaNova = Field(examples=["segredo123"])
