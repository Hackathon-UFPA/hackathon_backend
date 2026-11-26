from uuid import UUID

from fastapi import HTTPException, status


def projeto_final_nao_encontrado():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Projeto final não encontrado."
    )


def equipe_nao_encontrada_no_hackathon():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Equipe não encontrada neste hackathon.",
    )


def avaliador_tecnico_nao_encontrado():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Avaliador do Comitê Técnico não encontrado nesta organização.",
    )


def quantidade_tecnica_nao_configurada():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Configure a quantidade de avaliadores por projeto final antes de distribuir.",
    )


def resultado_cientifico_nao_homologado():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "O resultado da avaliação científica ainda não foi homologado: "
            "não há projetos finais para designar."
        ),
    )


def hackathon_encerrado():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "O hackathon foi finalizado ou cancelado: não é mais possível "
            "designar ou redistribuir projetos finais."
        ),
    )


def avaliadores_tecnicos_insuficientes(n: int, submissao_id: UUID, disponiveis: int):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"O projeto {submissao_id} precisa de {n} avaliadores do Comitê Técnico, mas só "
            f"{disponiveis} estão disponíveis sem conflito de interesse. Nada foi designado."
        ),
    )


def quantidade_de_avaliadores_tecnicos_invalida(n: int):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Informe exatamente {n} avaliadores, sem repetir.",
    )


def avaliadores_tecnicos_nao_elegiveis():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Todos os avaliadores precisam ser do Comitê Técnico, com conta ativa, "
            "da organização do hackathon."
        ),
    )


def avaliador_em_conflito(ids: list[UUID]):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Conflito de interesse (integrante, mentor ou conflito declarado com a equipe): "
            + ", ".join(str(i) for i in ids)
        ),
    )


def conflito_ja_registrado():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Este conflito de interesse já está registrado.",
    )


def conflito_com_designacao_vigente():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "O avaliador está designado ao projeto desta equipe. "
            "Redistribua o projeto antes de registrar o conflito."
        ),
    )
