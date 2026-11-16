from fastapi import HTTPException, status


def consulta_apenas_por_integrante():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Apenas integrantes da equipe podem consultá-la.",
    )


def equipe_nao_editavel():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A equipe só pode ser editada enquanto está em formação.",
    )


def membro_nao_encontrado():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Membro não encontrado nesta equipe.",
    )


def lider_protegido():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="O líder não pode ser removido ou rebaixado, nem outro membro promovido a líder. "
        "Transferência de liderança ainda não está disponível.",
    )


def composicao_invalida(mensagem: str):
    """A composição informada pelo líder não fecha (limites, duplicidade, categoria, tipos)."""
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=mensagem)


def categoria_nao_permitida(permitidas: list[str]):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Esta edição não aceita equipes da categoria escolhida. "
        f"Categorias aceitas: {', '.join(permitidas)}.",
    )


def reconvite_indisponivel(emails: list[str]):
    """O índice uq_convites_equipe_email_ativo ainda impede reconvidar quem já aceitou e saiu."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Estas pessoas já aceitaram um convite desta equipe e foram removidas; "
        f"o reconvite à mesma equipe ainda não está disponível: {', '.join(emails)}.",
    )
