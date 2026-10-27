from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

from app.const.config import settings
from app.security.token import ALGORITMO, criar_token, ler_token


def token_com(claims: dict, chave: str = settings.JWT_SECRET) -> str:
    return jwt.encode(claims, chave, algorithm=ALGORITMO)


def test_token_devolve_o_id_do_usuario():
    usuario_id = uuid4()

    assert ler_token(criar_token(usuario_id)) == usuario_id


def test_token_expira_no_prazo_configurado():
    claims = jwt.decode(criar_token(uuid4()), settings.JWT_SECRET, algorithms=[ALGORITMO])

    duracao = claims["exp"] - claims["iat"]
    assert duracao == settings.JWT_EXPIRE_MINUTES * 60


def test_token_vencido():
    vencido = datetime.now(UTC) - timedelta(seconds=1)

    assert ler_token(token_com({"sub": str(uuid4()), "exp": vencido})) is None


def test_token_assinado_com_outra_chave():
    valido_ate = datetime.now(UTC) + timedelta(minutes=5)
    token = token_com({"sub": str(uuid4()), "exp": valido_ate}, chave="x" * 32)

    assert ler_token(token) is None


def test_token_adulterado():
    token = criar_token(uuid4())
    corpo_alterado = token.split(".")[1][::-1]
    adulterado = ".".join([token.split(".")[0], corpo_alterado, token.split(".")[2]])

    assert ler_token(adulterado) is None


def test_token_sem_expiracao():
    assert ler_token(token_com({"sub": str(uuid4())})) is None


def test_token_com_id_invalido():
    valido_ate = datetime.now(UTC) + timedelta(minutes=5)

    assert ler_token(token_com({"sub": "nao-e-um-uuid", "exp": valido_ate})) is None


def test_texto_qualquer_nao_e_token():
    assert ler_token("isto nao e um token") is None
