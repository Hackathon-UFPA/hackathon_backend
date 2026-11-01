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


def equipe_nao_homologada():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Somente equipes HOMOLOGADA podem enviar uma proposta.",
    )


def proposta_ja_enviada():
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposta já enviada.")


def fora_do_periodo_de_propostas():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Envio fora do período de propostas ou prazo não configurado.",
    )


def proposta_incompleta(campos: list[str]):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Campos obrigatórios da proposta incompletos ou inválidos: {', '.join(campos)}.",
    )


def proposta_enviada_nao_encontrada():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Proposta enviada não encontrada."
    )
