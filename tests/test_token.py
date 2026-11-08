from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

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


def test_token_guarda_apenas_identificador_e_datas_sem_dados_do_perfil():
    usuario_id = uuid4()

    claims = jwt.decode(criar_token(usuario_id), settings.JWT_SECRET, algorithms=[ALGORITMO])

    assert set(claims) == {"sub", "iat", "exp"}
    assert claims["sub"] == str(usuario_id)
    assert claims["iat"] < claims["exp"]


def test_token_sem_identificador_do_usuario():
    valido_ate = datetime.now(UTC) + timedelta(minutes=5)

    assert ler_token(token_com({"exp": valido_ate})) is None


@pytest.mark.parametrize("identificador", [123, None, ["usuario"]])
def test_token_rejeita_identificador_que_nao_seja_texto(identificador):
    valido_ate = datetime.now(UTC) + timedelta(minutes=5)

    assert ler_token(token_com({"sub": identificador, "exp": valido_ate})) is None


@pytest.mark.parametrize("algoritmo", ["HS384", "HS512"])
def test_token_rejeita_algoritmo_diferente_mesmo_com_a_chave_correta(monkeypatch, algoritmo):
    monkeypatch.setattr(settings, "JWT_SECRET", "chave-exclusiva-deste-teste-" * 3)
    claims = {"sub": str(uuid4()), "exp": datetime.now(UTC) + timedelta(minutes=5)}
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm=algoritmo)

    assert ler_token(token) is None


def test_token_sem_assinatura_e_rejeitado():
    claims = {"sub": str(uuid4()), "exp": datetime.now(UTC) + timedelta(minutes=5)}
    token = jwt.encode(claims, "", algorithm="none")

    assert ler_token(token) is None


@pytest.mark.parametrize("campo", ["nbf", "iat"])
def test_token_ainda_nao_valido_e_rejeitado(campo):
    futuro = datetime.now(UTC) + timedelta(hours=1)
    token = token_com({"sub": str(uuid4()), "exp": futuro + timedelta(hours=1), campo: futuro})

    assert ler_token(token) is None


def test_token_com_expiracao_nao_numerica_e_rejeitado():
    assert ler_token(token_com({"sub": str(uuid4()), "exp": "amanha"})) is None
