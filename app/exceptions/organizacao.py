from fastapi import HTTPException, status


def organizacao_nao_encontrada():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organização não encontrada.")
