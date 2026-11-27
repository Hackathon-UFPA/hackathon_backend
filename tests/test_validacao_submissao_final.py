import asyncio
from io import BytesIO
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from pypdf import PdfWriter

from app.validations import submissao_final as validacao

pytestmark = pytest.mark.unit

REPOSITORIO = "https://github.com/Equipe/Projeto"


@pytest.fixture
def simular_github(monkeypatch):
    cliente_http = httpx.AsyncClient

    def configurar(responder):
        chamadas = Mock(side_effect=responder)

        def cliente(**opcoes):
            return cliente_http(transport=httpx.MockTransport(chamadas), **opcoes)

        monkeypatch.setattr(validacao.httpx, "AsyncClient", cliente)
        return chamadas

    return configurar


@pytest.mark.parametrize(
    "url",
    [REPOSITORIO, " https://github.com/Equipe/Projeto.git/ ", "HTTPS://GITHUB.COM/Equipe/Projeto"],
)
def test_normalizar_repositorio(url):
    assert validacao.normalizar_repositorio(url) == REPOSITORIO


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/Equipe/Projeto",
        "https://gitlab.com/Equipe/Projeto",
        f"{REPOSITORIO}/issues",
        f"{REPOSITORIO}?tab=readme",
        "https://github.com/Equipe/..",
        "https://github.com/Equipe/.git",
    ],
)
def test_rejeitar_url_fora_do_formato_de_repositorio(url):
    with pytest.raises(ValueError, match="repositório GitHub"):
        validacao.normalizar_repositorio(url)


def test_confirmar_repositorio_publico_pela_api(simular_github):
    chamadas = simular_github(
        lambda _: httpx.Response(200, json={"full_name": "equipe/projeto", "private": False})
    )

    asyncio.run(validacao.validar_repositorio(REPOSITORIO))

    chamadas.assert_called_once()
    requisicao = chamadas.call_args.args[0]
    assert requisicao.method == "GET"
    assert str(requisicao.url) == "https://api.github.com/repos/Equipe/Projeto"
    assert requisicao.headers["Accept"] == "application/vnd.github+json"


@pytest.mark.parametrize("codigo", [301, 404, 410, 451])
def test_rejeitar_repositorio_inacessivel_sem_seguir_redirecionamento(simular_github, codigo):
    chamadas = simular_github(
        lambda _: httpx.Response(codigo, headers={"Location": "/repos/Equipe/Novo"})
    )

    with pytest.raises(HTTPException) as erro:
        asyncio.run(validacao.validar_repositorio(REPOSITORIO))

    assert erro.value.status_code == 422
    chamadas.assert_called_once()


@pytest.mark.parametrize(
    "dados",
    [
        {"full_name": "Equipe/Outro", "private": False},
        {"full_name": "Equipe/Projeto", "private": True},
        {"full_name": "Equipe/Projeto", "private": False, "disabled": True},
        {"full_name": "Equipe/Projeto"},
    ],
    ids=["identidade-distinta", "privado", "desativado", "visibilidade-desconhecida"],
)
def test_rejeitar_metadados_sem_confirmacao_de_repositorio_publico(simular_github, dados):
    simular_github(lambda _: httpx.Response(200, json=dados))

    with pytest.raises(HTTPException) as erro:
        asyncio.run(validacao.validar_repositorio(REPOSITORIO))

    assert erro.value.status_code == 422


@pytest.mark.parametrize(
    ("codigo", "corpo"),
    [
        (429, b""),
        (502, b""),
        (200, b"indisponivel"),
        (200, b'{"private": false}'),
        (200, b'{"full_name": 1, "private": false}'),
        (200, b" " * (validacao.LIMITE_RESPOSTA_GITHUB + 1)),
    ],
    ids=["limite-da-api", "servidor", "json-invalido", "sem-nome", "tipo-do-nome", "corpo-grande"],
)
def test_falha_temporaria_na_resposta_do_github(simular_github, codigo, corpo):
    simular_github(lambda _: httpx.Response(codigo, content=corpo))

    with pytest.raises(HTTPException) as erro:
        asyncio.run(validacao.validar_repositorio(REPOSITORIO))

    assert erro.value.status_code == 503


def test_timeout_na_consulta_ao_github(simular_github):
    def expirar(requisicao):
        raise httpx.ReadTimeout("tempo esgotado", request=requisicao)

    simular_github(expirar)
    with pytest.raises(HTTPException) as erro:
        asyncio.run(validacao.validar_repositorio(REPOSITORIO))

    assert erro.value.status_code == 503


async def fluxo(*blocos: bytes):
    for bloco in blocos:
        yield bloco


def criar_pdf(*, paginas: int = 1, senha: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(paginas):
        writer.add_blank_page(width=72, height=72)
    if senha is not None:
        writer.encrypt(senha)
    with BytesIO() as arquivo:
        writer.write(arquivo)
        return arquivo.getvalue()


def test_ler_pdf_em_blocos_no_limite(monkeypatch):
    pdf = criar_pdf()
    monkeypatch.setattr(validacao, "LIMITE_RELATORIO", len(pdf))

    lido = asyncio.run(
        validacao.ler_relatorio_pdf(fluxo(pdf[:16], pdf[16:]), "Application/PDF; x=1")
    )

    assert lido == pdf


def test_limite_do_pdf_considera_a_soma_dos_blocos(monkeypatch):
    monkeypatch.setattr(validacao, "LIMITE_RELATORIO", 8)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(validacao.ler_relatorio_pdf(fluxo(b"%PDF-", b"1.7\n"), "application/pdf"))

    assert erro.value.status_code == 413


def test_tipo_de_midia_incorreto_rejeita_pdf_valido():
    with pytest.raises(HTTPException) as erro:
        asyncio.run(validacao.ler_relatorio_pdf(fluxo(criar_pdf()), "application/octet-stream"))

    assert erro.value.status_code == 415


@pytest.mark.parametrize(
    "gerar_pdf",
    [
        pytest.param(lambda: b"%PDF-1.7\nconteudo truncado", id="corrompido"),
        pytest.param(lambda: criar_pdf(paginas=0), id="sem-paginas"),
        pytest.param(lambda: criar_pdf(senha="teste"), id="com-senha"),
    ],
)
def test_rejeitar_pdfs_ilegiveis(gerar_pdf):
    with pytest.raises(HTTPException) as erro:
        asyncio.run(validacao.ler_relatorio_pdf(fluxo(gerar_pdf()), "application/pdf"))

    assert erro.value.status_code == 422
