from fastapi import HTTPException


def conflito_mentoria(mensagem: str):
    raise HTTPException(409, mensagem)


def atribuicao_nao_encontrada():
    raise HTTPException(404, "A equipe não possui atribuição de mentor vigente.")
