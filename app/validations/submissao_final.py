import asyncio
import json
import re
from collections.abc import AsyncIterable
from io import BytesIO

import httpx
from fastapi import HTTPException, status
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from starlette.concurrency import run_in_threadpool

LIMITE_RELATORIO = 10 * 1024 * 1024
LIMITE_RESPOSTA_GITHUB = 64 * 1024
GITHUB = "https://github.com"
API_GITHUB = "https://api.github.com"
_LINK_GITHUB = re.compile(
    r"https://github\.com/([a-z0-9][a-z0-9-]{0,38})/([a-z0-9_.-]{1,100})/?",
    re.IGNORECASE | re.ASCII,
)


def normalizar_repositorio(url: str) -> str:
    match = _LINK_GITHUB.fullmatch(url.strip())
    if match is not None:
        dono, repositorio = match.groups()
        repositorio = repositorio.removesuffix(".git")
        if repositorio not in ("", ".", ".."):
            return f"{GITHUB}/{dono}/{repositorio}"
    raise ValueError("Informe o endereço HTTPS de um repositório GitHub (dono/repositório).")


async def validar_repositorio(url: str) -> None:
    """Valida o repositório informado usando somente a API oficial e pública do GitHub."""
    nome = url.removeprefix(f"{GITHUB}/")
    try:
        async with (
            asyncio.timeout(5),
            httpx.AsyncClient(
                base_url=API_GITHUB,
                follow_redirects=False,
                trust_env=False,
                timeout=4,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Accept-Encoding": "identity",
                    "X-GitHub-Api-Version": "2026-03-10",
                },
            ) as client,
            client.stream("GET", f"/repos/{nome}") as resposta,
        ):
            if resposta.is_redirect or resposta.status_code in (404, 410, 451):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="O link deve apontar diretamente para um repositório público acessível.",
                )
            resposta.raise_for_status()
            corpo = bytearray()
            async for bloco in resposta.aiter_bytes():
                if len(corpo) + len(bloco) > LIMITE_RESPOSTA_GITHUB:
                    raise ValueError("Resposta do GitHub excede o limite.")
                corpo.extend(bloco)
            dados = json.loads(corpo)
            nome_confirmado = dados["full_name"]
            if not isinstance(nome_confirmado, str):
                raise ValueError("Resposta do GitHub sem identificação do repositório.")
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError, RecursionError) as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível validar o repositório no GitHub. Tente novamente.",
        ) from erro

    if (
        nome_confirmado.casefold() != nome.casefold()
        or dados.get("private") is not False
        or dados.get("disabled") is True
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O link deve apontar diretamente para um repositório público acessível.",
        )


def _validar_pdf(arquivo: BytesIO) -> None:
    leitor = PdfReader(arquivo, strict=True)
    if leitor.is_encrypted or not len(leitor.pages):
        raise PdfReadError("O PDF deve ser legível e conter páginas.")


async def ler_relatorio_pdf(stream: AsyncIterable[bytes], content_type: str) -> bytes:
    if content_type.partition(";")[0].strip().lower() != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Envie o relatório com Content-Type: application/pdf.",
        )
    with BytesIO() as arquivo:
        async for bloco in stream:
            if arquivo.tell() + len(bloco) > LIMITE_RELATORIO:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="O relatório deve ter até 10 MB.",
                )
            arquivo.write(bloco)
        arquivo.seek(0)
        try:
            await run_in_threadpool(_validar_pdf, arquivo)
        except (PdfReadError, ValueError, TypeError, KeyError, RecursionError, IndexError) as erro:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Envie um PDF legível, com pelo menos uma página e sem senha.",
            ) from erro
        return arquivo.getvalue()
