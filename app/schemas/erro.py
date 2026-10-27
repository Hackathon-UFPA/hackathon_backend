from pydantic import BaseModel, Field


class ErroResponse(BaseModel):
    """Formato de erro da API. Erros de validação (422) seguem o padrão do FastAPI: uma lista
    em `detail`, com `loc` apontando o campo e `msg` explicando o problema."""

    detail: str = Field(examples=["E-mail ou senha inválidos."])
