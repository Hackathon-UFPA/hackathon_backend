from fastapi import HTTPException, status


def consulta_apenas_por_integrante():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Apenas integrantes da equipe podem consultá-la.",
    )


def equipe_nao_editavel():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A equipe só pode ser editada enquanto está em formação.",
    )
