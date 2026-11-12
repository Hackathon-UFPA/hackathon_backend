from fastapi import HTTPException


def mentor_nao_encontrado():
    raise HTTPException(404, "Mentor não encontrado.")


def convite_invalido():
    raise HTTPException(400, "Convite inválido, expirado ou já utilizado.")


def mentor_inelegivel():
    raise HTTPException(409, "Mentor inativo ou com perfil e termos ainda pendentes (RN33).")
