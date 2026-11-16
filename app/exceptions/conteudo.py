from fastapi import HTTPException, status


def item_nao_encontrado(nome: str):
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"{nome} não encontrado.")


def conteudo_invalido(mensagem: str):
    raise HTTPException(422, mensagem)


def conflito_de_conteudo(mensagem: str):
    raise HTTPException(status.HTTP_409_CONFLICT, mensagem)


def acesso_ao_treinamento_negado():
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "O treinamento é exclusivo das equipes aprovadas e da organização.",
    )
