import logging

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def instancia_nao_encontrada(nome=""):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Instancia {nome} nao encontrada!"
    )


def erro_de_integridade_sql(error):
    mensagem_de_erro = str(error.orig)
    logger.error(mensagem_de_erro)
    if "unique constraint" in mensagem_de_erro:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Violacao de unique constraint!"
        )
    elif "check constraint" in mensagem_de_erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Check constraint violada!"
        )
    elif "foreign key constraint" in mensagem_de_erro:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Foreign key constraint violada!"
        )
    else:
        raise HTTPException(status_code=500, detail="Erro do banco de dados nao documentado!")
