"""Exceptions da conferência de comprovantes e da conclusão da inscrição (RF21 a RF23)."""

from fastapi import HTTPException, status


def comprovante_nao_encontrado():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comprovante não encontrado.")


def comprovante_ja_decidido():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Este comprovante já foi aprovado ou recusado.",
    )


def comprovante_ativo_existente():
    """Só se reenvia depois de uma recusa: há no máximo um comprovante em aberto ou aprovado."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Você já tem um comprovante pendente ou aprovado neste hackathon.",
    )


def inscricao_ja_concluida():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A inscrição desta equipe já foi concluída.",
    )


def requisitos_nao_cumpridos(mensagens: list[str]):
    """A lista completa de pendências está em `GET /equipes/{id}/painel`."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A inscrição ainda não pode ser concluída: " + " ".join(mensagens),
    )
