"""Exceptions dos convites e dos aceites de termos (RF18, RF19, RF20)."""

from fastapi import HTTPException, status


def equipe_nao_encontrada():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipe não encontrada.")


def convite_nao_encontrado():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite não encontrado.")


def hackathon_nao_encontrado():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hackathon não encontrado.")


def apenas_lider_da_equipe():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Apenas o líder técnico da equipe pode fazer isto.",
    )


def apenas_integrante_da_equipe():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Apenas integrantes da equipe podem consultar os convites.",
    )


def fora_do_periodo_de_inscricao():
    """RN06: convites só valem enquanto as inscrições estão abertas."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="As inscrições deste hackathon não estão abertas.",
    )


def equipe_sem_vagas(maximo: int):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"A equipe já tem o máximo de {maximo} integrantes (convites pendentes contam).",
    )


def convite_repetido():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Já existe um convite pendente ou aceito para este e-mail nesta equipe.",
    )


def ja_e_integrante():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Esta pessoa já é integrante da equipe."
    )


def convite_ja_respondido():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Este convite não está mais pendente.",
    )


def ja_esta_em_outra_equipe():
    """RN02: uma pessoa participa de uma única equipe por hackathon."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Você já faz parte de uma equipe neste hackathon.",
    )


def termos_nao_publicados():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="O regulamento e o termo de consentimento vigentes ainda não foram publicados.",
    )


def termos_desatualizados():
    """O texto aceito precisa ser a versão vigente: se mudou, a pessoa lê e aceita de novo."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Os termos aceitos não são os vigentes. Leia as versões atuais e aceite de novo.",
    )


def aceite_incompleto():
    """RN05: é preciso aceitar o regulamento e o termo de consentimento."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="É preciso aceitar o regulamento e o termo de consentimento vigentes.",
    )
