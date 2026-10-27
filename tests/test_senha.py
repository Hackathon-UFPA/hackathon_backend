import pytest

from app.security.senha import (
    gastar_tempo_de_verificacao,
    gerar_hash,
    senha_confere,
    validar_forca_da_senha,
)


def test_senha_valida():
    assert validar_forca_da_senha("segredo123") == "segredo123"


@pytest.mark.parametrize(
    "senha, motivo",
    [
        ("abc123", "pelo menos 8 caracteres"),
        ("somenteletras", "uma letra e um número"),
        ("12345678", "uma letra e um número"),
        ("________1", "uma letra e um número"),
    ],
)
def test_senha_fraca(senha, motivo):
    with pytest.raises(ValueError, match=motivo):
        validar_forca_da_senha(senha)


def test_hash_nao_guarda_a_senha_e_confere():
    senha_hash = gerar_hash("segredo123")

    assert "segredo123" not in senha_hash
    assert senha_hash.startswith("$argon2")
    assert senha_confere("segredo123", senha_hash)


def test_senha_errada_nao_confere():
    assert not senha_confere("outra-senha1", gerar_hash("segredo123"))


def test_hash_invalido_nao_confere():
    assert not senha_confere("segredo123", "isto nao e um hash")


def test_mesma_senha_gera_hashes_diferentes():
    assert gerar_hash("segredo123") != gerar_hash("segredo123")


def test_verificacao_falsa_nao_levanta_erro():
    gastar_tempo_de_verificacao("qualquer123")
