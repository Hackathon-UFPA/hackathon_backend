from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.const.config import settings

ALGORITMO = "HS256"


def criar_token(usuario_id: UUID, versao_sessao: int = 0) -> str:
    """Token de acesso: guarda o id do usuário e a versão da sessão (`sv`). O perfil é lido do
    banco a cada pedido, então desativar uma conta ou trocar o perfil vale na hora; e aumentar a
    versão da sessão no banco invalida de uma vez todos os tokens emitidos antes (BE-S5-07)."""
    agora = datetime.now(UTC)
    claims = {
        "sub": str(usuario_id),
        "sv": versao_sessao,
        "iat": agora,
        "exp": agora + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=ALGORITMO)


def _decodificar(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[ALGORITMO],
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError:
        return None


def ler_sessao(token: str) -> tuple[UUID, int] | None:
    """Devolve o id do usuário e a versão da sessão, ou None se o token for inválido,
    adulterado ou estiver vencido. Token sem `sv` (emitido antes da BE-S5-07) vale como 0."""
    claims = _decodificar(token)
    if claims is None:
        return None
    try:
        versao = claims.get("sv", 0)
        if isinstance(versao, bool) or not isinstance(versao, int):
            return None
        return UUID(claims["sub"]), versao
    except (ValueError, TypeError):
        return None


def ler_token(token: str) -> UUID | None:
    """Devolve o id do usuário, ou None se o token for inválido, adulterado ou estiver vencido."""
    sessao = ler_sessao(token)
    return sessao[0] if sessao else None


def segundos_restantes(token: str) -> int | None:
    """Quanto falta para o token vencer (RF09); None se o token for inválido."""
    claims = _decodificar(token)
    if claims is None:
        return None
    restante = int(claims["exp"] - datetime.now(UTC).timestamp())
    return max(restante, 0)
