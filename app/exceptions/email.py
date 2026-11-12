from fastapi import HTTPException, status

from app.const.enums import StatusEmail


def email_nao_encontrado():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado.")


def email_cancelado():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Mensagem cancelada por revogação do convite. Emita um novo convite de mentor.",
    )


def reenvio_nao_permitido(situacao: StatusEmail):
    if situacao == StatusEmail.ENVIADO:
        detalhe = "Este e-mail já foi enviado: reenviar duplicaria o aviso."
    else:
        detalhe = "Este e-mail ainda está na fila de envio. Só é possível reenviar os que falharam."
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalhe)
