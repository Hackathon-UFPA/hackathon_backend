from fastapi import HTTPException


def feedback_invalido(mensagem: str):
    raise HTTPException(422, mensagem)
