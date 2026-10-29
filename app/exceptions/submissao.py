from fastapi import HTTPException, status


def proposta_ja_existente():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Já existe uma proposta para esta equipe."
    )


def rascunho_nao_encontrado():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Rascunho de proposta não encontrado."
    )


def proposta_nao_editavel():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Uma proposta enviada não pode ser editada."
    )


def equipe_somente_leitura():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Equipes com situação NAO_HOMOLOGADA só podem consultar a proposta.",
    )


def tema_nao_encontrado():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tema não encontrado.")


def tema_nao_disponivel():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="O tema deve estar ativo e pertencer ao mesmo hackathon da equipe.",
    )
