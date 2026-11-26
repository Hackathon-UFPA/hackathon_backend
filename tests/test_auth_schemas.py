"""Validação de dados de cadastro e login diretamente nos schemas Pydantic."""

import pytest
from pydantic import ValidationError

from app.const.enums import TipoIntegrante
from app.schemas.auth import CadastroRequest, LoginRequest

pytestmark = pytest.mark.unit


@pytest.fixture
def cadastro():
    return {
        "nome": "Maria da Silva",
        "email": "maria@example.com",
        "senha": "segredo123",
        "instituicao": "UFPA",
        "curso": "Sistemas de Informação",
        "periodo": 5,
        "comprovante_url": "https://example.com/comprovante.pdf",
    }


@pytest.mark.parametrize("campo", ["nome", "instituicao", "curso"])
def test_textos_do_cadastro_removem_espacos_nas_extremidades(cadastro, campo):
    cadastro[campo] = "  Valor válido  "

    dados = CadastroRequest.model_validate(cadastro)

    assert getattr(dados, campo) == "Valor válido"


@pytest.mark.parametrize("campo", ["nome", "instituicao", "curso"])
@pytest.mark.parametrize("valor", ["", "   ", "x" * 256])
def test_textos_do_cadastro_rejeitam_vazios_e_excesso_de_caracteres(cadastro, campo, valor):
    cadastro[campo] = valor

    with pytest.raises(ValidationError) as erro:
        CadastroRequest.model_validate(cadastro)

    assert erro.value.errors()[0]["loc"] == (campo,)


@pytest.fixture
def cadastro_profissional(cadastro):
    for campo in ("instituicao", "curso", "periodo"):
        cadastro.pop(campo)
    return {**cadastro, "tipo": "PROFISSIONAL", "organizacao": " UFPA ", "cargo": " Analista "}


def test_profissional_informa_empresa_e_cargo_no_lugar_de_dados_academicos(cadastro_profissional):
    dados = CadastroRequest.model_validate(cadastro_profissional)

    assert dados.tipo == TipoIntegrante.PROFISSIONAL
    assert (dados.organizacao, dados.cargo) == ("UFPA", "Analista")
    assert (dados.instituicao, dados.curso, dados.periodo) == (None, None, None)


@pytest.mark.parametrize("campo", ["organizacao", "cargo"])
def test_profissional_precisa_dos_dois_dados_de_vinculo(cadastro_profissional, campo):
    cadastro_profissional.pop(campo)

    with pytest.raises(ValidationError, match=f"informe: {campo}"):
        CadastroRequest.model_validate(cadastro_profissional)


@pytest.mark.parametrize(("campo", "valor"), [("instituicao", "UFPA"), ("periodo", 1)])
def test_profissional_recusa_dados_academicos(cadastro_profissional, campo, valor):
    with pytest.raises(ValidationError, match=f"não informe: {campo}"):
        CadastroRequest.model_validate({**cadastro_profissional, campo: valor})


def test_cadastro_legado_e_estudante_e_recusa_cargo(cadastro):
    assert CadastroRequest.model_validate(cadastro).tipo == TipoIntegrante.ESTUDANTE

    with pytest.raises(ValidationError, match="não informe: cargo"):
        CadastroRequest.model_validate({**cadastro, "cargo": "Analista"})


@pytest.mark.parametrize("periodo", [0, -1])
def test_periodo_precisa_ser_positivo(cadastro, periodo):
    cadastro["periodo"] = periodo

    with pytest.raises(ValidationError) as erro:
        CadastroRequest.model_validate(cadastro)

    assert erro.value.errors()[0]["loc"] == ("periodo",)


@pytest.mark.parametrize("senha", ["a" * 7 + "1", "a" * 127 + "1"])
def test_senha_aceita_limites_de_oito_e_128_caracteres(cadastro, senha):
    cadastro["senha"] = senha

    assert CadastroRequest.model_validate(cadastro).senha == senha


@pytest.mark.parametrize("senha", ["a" * 6 + "1", "a" * 128 + "1", "abcdefgh", "12345678"])
def test_cadastro_rejeita_senha_fora_do_tamanho_ou_sem_letra_e_numero(cadastro, senha):
    cadastro["senha"] = senha

    with pytest.raises(ValidationError) as erro:
        CadastroRequest.model_validate(cadastro)

    assert erro.value.errors()[0]["loc"] == ("senha",)


@pytest.mark.parametrize("extensao", ["pdf", "PNG", "jpg", "JPEG"])
def test_comprovante_aceita_extensoes_permitidas_com_query_e_fragmento(cadastro, extensao):
    url = f"https://example.com/arquivo.{extensao}?download=1#pagina-1"
    cadastro["comprovante_url"] = url

    assert str(CadastroRequest.model_validate(cadastro).comprovante_url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/arquivo.pdf",
        "https://example.com/arquivo.exe",
        "https://example.com/arquivo.pdf.exe",
        "https://example.com/arquivo?nome=comprovante.pdf",
        "https://example.com/",
        "arquivo.pdf",
    ],
)
def test_comprovante_rejeita_protocolo_e_caminho_invalidos(cadastro, url):
    cadastro["comprovante_url"] = url

    with pytest.raises(ValidationError) as erro:
        CadastroRequest.model_validate(cadastro)

    assert erro.value.errors()[0]["loc"] == ("comprovante_url",)


def test_cadastro_nao_aceita_perfil_privilegiado_enviado_pelo_cliente(cadastro):
    cadastro["papel"] = "DEV"

    assert "papel" not in CadastroRequest.model_validate(cadastro).model_dump()


@pytest.mark.parametrize("senha", ["x", "123", "senha-antiga", "a" * 128])
def test_login_aceita_senha_antiga_sem_aplicar_regra_de_forca(senha):
    assert LoginRequest(email="maria@example.com", senha=senha).senha == senha


@pytest.mark.parametrize("senha", ["", "a" * 129])
def test_login_rejeita_senha_vazia_ou_acima_do_limite(senha):
    with pytest.raises(ValidationError) as erro:
        LoginRequest(email="maria@example.com", senha=senha)

    assert erro.value.errors()[0]["loc"] == ("senha",)
