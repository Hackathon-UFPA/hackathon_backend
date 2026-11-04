from fastapi import HTTPException, status


def resultado_ja_homologado():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "O resultado da avaliação deste hackathon já foi homologado e está bloqueado: "
            "não é mais possível alterar avaliações, designações ou o resultado."
        ),
    )


def avaliacoes_nao_concluidas(pendencias: int):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Só é possível homologar quando todas as avaliações estiverem concluídas. Há "
            f"{pendencias} pendência(s): consulte GET /admin/hackathons/{{id}}/resultado."
        ),
    )


def aprovadas_invalidas(motivo: str):
    raise HTTPException(status_code=422, detail=motivo)


def equipe_somente_leitura_apos_resultado():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "A proposta desta equipe não foi aprovada no resultado do hackathon. A equipe "
            "está em modo somente leitura: só pode consultar o painel, a proposta e o parecer."
        ),
    )


def resultado_da_equipe_nao_encontrado():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="A equipe não tem proposta com resultado homologado neste hackathon.",
    )
