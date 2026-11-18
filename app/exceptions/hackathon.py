from fastapi import HTTPException, status


def selecao_de_hackathon_ambigua():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Há mais de um hackathon com inscrições abertas. Informe hackathon_id "
            "para selecionar a edição."
        ),
    )


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
