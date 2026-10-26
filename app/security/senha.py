import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

SENHA_MIN_CARACTERES = 8
SENHA_MAX_CARACTERES = 128

_hasher = PasswordHasher()

# Hash de uma senha que ninguém tem. Serve para gastar o mesmo tempo de uma verificação real
# quando o e-mail não existe, para o tempo de resposta não revelar quais e-mails estão cadastrados.
_HASH_FALSO = _hasher.hash("senha-que-nao-pertence-a-ninguem")


def validar_forca_da_senha(senha: str) -> str:
    """Regra do cadastro (RF01): mínimo de 8 caracteres, com ao menos uma letra e um número."""
    if len(senha) < SENHA_MIN_CARACTERES:
        raise ValueError(f"A senha deve ter pelo menos {SENHA_MIN_CARACTERES} caracteres")
    if not re.search(r"[^\W\d_]", senha) or not re.search(r"\d", senha):
        raise ValueError("A senha deve ter pelo menos uma letra e um número")
    return senha


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def senha_confere(senha: str, senha_hash: str) -> bool:
    try:
        return _hasher.verify(senha_hash, senha)
    except (VerificationError, InvalidHashError):
        return False


def gastar_tempo_de_verificacao(senha: str) -> None:
    senha_confere(senha, _HASH_FALSO)
