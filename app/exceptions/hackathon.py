from fastapi import HTTPException, status


def periodo_invalido(mensagem: str):
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=mensagem)


def hackathon_com_dados_ligados():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "O hackathon tem dados ligados a ele (equipes, temas, termos, rubrica ou "
            "inscrições) e não pode ser excluído; cancele-o alterando o status para CANCELADO."
        ),
    )
