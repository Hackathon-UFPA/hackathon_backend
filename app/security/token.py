from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.const.config import settings

ALGORITMO = "HS256"


def criar_token(usuario_id: UUID) -> str:
    """Token de acesso: guarda só o id do usuário. O perfil é lido do banco a cada pedido,
    então desativar uma conta ou trocar o perfil vale na hora."""
    agora = datetime.now(UTC)
    claims = {
        "sub": str(usuario_id),
        "iat": agora,
        "exp": agora + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=ALGORITMO)


def ler_token(token: str) -> UUID | None:
    """Devolve o id do usuário, ou None se o token for inválido, adulterado ou estiver vencido."""
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[ALGORITMO],
            options={"require": ["sub", "exp"]},
        )
        return UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
