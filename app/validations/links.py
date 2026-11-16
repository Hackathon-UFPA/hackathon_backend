"""Política de links do conteúdo institucional (RNF20, BE-S5-12).

A API **não recebe nem guarda arquivos**: logos, regulamento em PDF e materiais do treinamento
ficam em um serviço externo (ex.: Cloudinary, Drive) e a API guarda só o link. Regras propostas,
a validar com o grupo (Q14): endereço `https`, até 2048 caracteres, sem espaços nem caracteres
de controle e sem usuário e senha embutidos. Logos precisam apontar para uma imagem.
"""

from urllib.parse import urlsplit

TAMANHO_MAXIMO_DO_LINK = 2048
EXTENSOES_DE_IMAGEM = (".png", ".jpg", ".jpeg", ".webp", ".svg")


def validar_link_https(valor: str) -> str:
    valor = valor.strip()
    if not valor or len(valor) > TAMANHO_MAXIMO_DO_LINK:
        raise ValueError(f"O link deve ter até {TAMANHO_MAXIMO_DO_LINK} caracteres")
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in valor):
        raise ValueError("O link não pode ter espaços nem caracteres de controle")
    try:
        partes = urlsplit(valor)
        _ = partes.port  # valida a porta
    except ValueError as erro:
        raise ValueError("Link inválido") from erro
    if partes.scheme != "https" or not partes.hostname:
        raise ValueError("O link deve usar https")
    if partes.username or partes.password:
        raise ValueError("O link não pode conter usuário e senha")
    return valor


def validar_link_de_imagem(valor: str) -> str:
    valor = validar_link_https(valor)
    if not urlsplit(valor).path.lower().endswith(EXTENSOES_DE_IMAGEM):
        raise ValueError("O logo deve ser uma imagem (png, jpg, jpeg, webp ou svg)")
    return valor
