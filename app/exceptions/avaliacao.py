from fastapi import HTTPException, status


def proposta_nao_encontrada():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposta não encontrada.")


def quantidade_nao_configurada():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Configure a quantidade de avaliadores por proposta antes de distribuir.",
    )


def avaliacao_ja_iniciada():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "A avaliação já começou (ou o hackathon foi finalizado ou cancelado): "
            "não é mais possível distribuir ou redistribuir propostas."
        ),
    )


def proposta_com_nota():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A proposta já tem avaliação iniciada e não pode ser redistribuída.",
    )


def proposta_nao_enviada():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Somente propostas ENVIADA podem ser distribuídas ou avaliadas.",
    )


def avaliadores_insuficientes(necessarios: int, elegiveis: int):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Avaliadores elegíveis insuficientes: são necessários {necessarios} por proposta "
            f"e há {elegiveis} disponíveis. Nenhuma designação foi gravada."
        ),
    )


def avaliadores_nao_elegiveis():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Todos os avaliadores precisam ser do Comitê Científico, com conta ativa. "
            "Nenhuma designação foi alterada."
        ),
    )


def quantidade_de_avaliadores_invalida(esperada: int):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Informe exatamente {esperada} avaliadores distintos para a proposta.",
    )


def avaliacao_nao_encontrada():
    raise HTTPException(status_code=404, detail="Avaliação não encontrada.")


def avaliacao_enviada():
    raise HTTPException(status_code=409, detail="A avaliação já foi enviada e é imutável.")


def rubrica_indisponivel():
    raise HTTPException(
        status_code=409, detail="A proposta exige rubrica publicada da mesma edição."
    )


def avaliacao_invalida(motivo: str):
    raise HTTPException(status_code=422, detail=motivo)
