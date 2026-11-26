import pytest

from app.validations.links import validar_link_de_imagem, validar_link_https

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("valor", ["http://example.com/a", "https:///sem-host"])
def test_link_exige_https_e_host(valor):
    with pytest.raises(ValueError, match="deve usar https"):
        validar_link_https(valor)


@pytest.mark.parametrize("autenticacao", ["usuario", "usuario:senha", ":senha"])
def test_link_rejeita_credenciais_embutidas(autenticacao):
    with pytest.raises(ValueError, match="não pode conter usuário e senha"):
        validar_link_https(f"https://{autenticacao}@example.com/a")


BASE = "https://assets.example.com/"


@pytest.mark.parametrize("tamanho", [2047, 2048])
def test_limite_de_tamanho_conta_o_link_apos_aparar_as_pontas(tamanho):
    link = BASE + "a" * (tamanho - len(BASE))

    assert validar_link_https(f" {link}\n") == link


def test_primeiro_tamanho_acima_do_limite_e_recusado():
    link = BASE + "a" * (2049 - len(BASE))

    with pytest.raises(ValueError, match="até 2048 caracteres"):
        validar_link_https(link)


@pytest.mark.parametrize(
    "caractere",
    [
        pytest.param("\x00", id="nulo"),
        pytest.param("\x1f", id="controle-ascii"),
        pytest.param("\x7f", id="delete"),
        pytest.param("\u00a0", id="espaco-inseparavel"),
    ],
)
def test_caracteres_de_controle_e_espacos_unicode_sao_recusados_no_meio_do_link(caractere):
    with pytest.raises(ValueError, match="espaços nem caracteres de controle"):
        validar_link_https(f"{BASE}lo{caractere}go.png")


@pytest.mark.parametrize("porta", ["abc", "65536"])
def test_porta_invalida_da_erro_de_validacao(porta):
    with pytest.raises(ValueError, match="^Link inválido$"):
        validar_link_https(f"https://assets.example.com:{porta}/logo.png")


@pytest.mark.parametrize("sufixo", ["?arquivo=logo.png", "#logo.png"])
def test_extensao_fora_do_caminho_nao_qualifica_link_como_imagem(sufixo):
    with pytest.raises(ValueError, match="logo deve ser uma imagem"):
        validar_link_de_imagem(f"{BASE}download{sufixo}")


def test_link_de_imagem_preserva_espaco_codificado_e_parametros():
    link = f"{BASE}logo%20principal.WEBP?versao=2#preview"

    assert validar_link_de_imagem(link) == link
