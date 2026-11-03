from fastapi import HTTPException, status


def titulo_de_tema_repetido():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Já existe um tema com este título neste hackathon.",
    )


def tema_com_propostas():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="O tema tem propostas ligadas a ele e não pode ser excluído; desative-o (RN04).",
    )
