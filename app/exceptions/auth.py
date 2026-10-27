from fastapi import HTTPException, status


def email_ja_cadastrado():
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado.")


def inscricoes_indisponiveis():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Não há hackathon com inscrições abertas no momento.",
    )


def credenciais_invalidas():
    """Mensagem genérica de propósito: não diz se o e-mail ou a senha está errado (RF02)."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="E-mail ou senha inválidos.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def conta_bloqueada(segundos_restantes: int):
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Muitas tentativas de login. Tente novamente mais tarde.",
        headers={"Retry-After": str(segundos_restantes)},
    )


def nao_autenticado():
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def acesso_negado():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Você não tem permissão para acessar este recurso.",
    )


def conta_pendente():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Conta pendente: aguarde a aprovação do comprovante de vínculo.",
    )
