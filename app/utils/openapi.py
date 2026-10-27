from app.schemas.erro import ErroResponse


def respostas_de_erro(descricoes: dict[int, str]) -> dict:
    """Monta o `responses` do FastAPI para documentar no Swagger os erros de uma rota."""
    return {
        codigo: {"model": ErroResponse, "description": texto}
        for codigo, texto in descricoes.items()
    }
