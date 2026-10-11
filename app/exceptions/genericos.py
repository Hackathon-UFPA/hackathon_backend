from fastapi import HTTPException


def erro_interno_do_servidor():
    raise HTTPException(status_code=500, detail="Erro interno do servidor!")


def dados_com_formato_errado():
    raise HTTPException(status_code=422, detail="Os dados não estão no formato apropriado.")
