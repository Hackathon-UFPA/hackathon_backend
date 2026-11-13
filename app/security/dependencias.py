from fastapi import Depends, HTTPException
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


# Para rotas públicas que mostram mais coisas a quem tem permissão: sem cabeçalho, segue como
# visitante; com cabeçalho, o token precisa ser válido (401 se não for), para o cliente não
# achar que está logado quando não está.
bearer_opcional = HTTPBearer(auto_error=False)


async def usuario_opcional(
    credenciais: HTTPAuthorizationCredentials | None = Depends(bearer_opcional),
    db: AsyncSession = Depends(get_session),
) -> Usuario | None:
    if credenciais is None:
        return None
    return await usuario_atual(credenciais, db)


async def usuario_ativo(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    """Exige RN33 concluída para mentor e comprovante aprovado para participante pendente."""
    if usuario.papel == PapelUsuario.MENTOR:
        if not usuario.mentor_ativado_em or not usuario.mentor_perfil_concluido_em:
            raise HTTPException(403, "Mentor pendente: conclua o perfil e aceite os termos (RN33).")
    elif usuario.situacao_conta == SituacaoConta.PENDENTE:
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
