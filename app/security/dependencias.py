from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, SituacaoConta
from app.db.db import get_session
from app.exceptions.auth import acesso_negado, conta_pendente, nao_autenticado
from app.models import Usuario
from app.security.token import ler_token

# auto_error=False para responder 401 (e não 403) quando o cabeçalho Authorization não vem
bearer = HTTPBearer(auto_error=False)


async def usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> Usuario:
    """Identifica quem faz o pedido. Aceita conta pendente: serve às rotas que ela pode usar."""
    if credenciais is None:
        nao_autenticado()
    usuario_id = ler_token(credenciais.credentials)
    if usuario_id is None:
        nao_autenticado()

    # O perfil e a situação vêm sempre do banco, não do token
    usuario = await db.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        nao_autenticado()
    return usuario


async def usuario_ativo(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    """Padrão das rotas protegidas: conta pendente (comprovante ainda não aprovado) fica de fora."""
    if usuario.situacao_conta == SituacaoConta.PENDENTE:
        conta_pendente()
    return usuario


def exigir_papeis(*papeis: PapelUsuario):
    """Dependência de rota que só deixa passar os perfis informados (RF06).
    DEV tem acesso a todas as rotas, como exceção criada para os testes da equipe."""
    permitidos = {*papeis, PapelUsuario.DEV}

    async def verificar(usuario: Usuario = Depends(usuario_ativo)) -> Usuario:
        if usuario.papel not in permitidos:
            acesso_negado()
        return usuario

    return verificar
