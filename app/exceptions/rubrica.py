from fastapi import HTTPException, status


def rubrica_nao_encontrada():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubrica não encontrada.")


def rubrica_nao_publicada():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="A rubrica ainda não foi publicada."
    )


def rubrica_publicada():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A rubrica já foi publicada e não pode mais ser alterada (RN09).",
    )


def fora_do_prazo_de_publicacao():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A rubrica precisa ser publicada antes do início das inscrições (RF17).",
    )


def rubrica_incompleta(pendencias: list[str]):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="A rubrica não pode ser publicada: " + " ".join(pendencias),
    )
