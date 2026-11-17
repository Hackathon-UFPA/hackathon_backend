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


def senha_atual_incorreta():
    """403 (e não 401): a sessão está válida, o que falhou foi a confirmação da senha. Um 401
    faria a interface derrubar a sessão por engano."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Senha atual incorreta.",
    )


def link_invalido():
    """Mesma resposta para token inexistente, vencido ou já usado, para não ajudar quem tenta
    adivinhar."""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Link inválido, expirado ou já utilizado.",
    )


def email_ja_confirmado():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="O e-mail desta conta já está confirmado.",
    )


def usuario_nao_encontrado():
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")


def gestao_de_mentor_em_rota_propria():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Mentores seguem o fluxo próprio (RN33): use as rotas de /admin/mentores para "
            "editar, desativar ou reativar."
        ),
    )


def troca_de_papel_nao_permitida():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Esta troca de perfil não é permitida: só é possível alternar entre Comitê Técnico, "
            "Comitê Científico e Organizador."
        ),
    )


def operacao_sobre_si_mesmo():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Você não pode alterar o próprio perfil nem desativar a própria conta por aqui.",
    )


def ultimo_organizador():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Esta é a única conta ativa de Organizador: o sistema não pode ficar sem uma.",
    )


def outra_organizacao():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Este hackathon pertence a outra organização.",
    )


def sem_organizacao():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Sua conta não está ligada a uma organização.",
    )
