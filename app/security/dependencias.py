from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, SituacaoConta
from app.db.db import get_session
from app.exceptions.auth import acesso_negado, conta_pendente, nao_autenticado
from app.models import Usuario
from app.security.token import ler_sessao

# auto_error=False para responder 401 (e não 403) quando o cabeçalho Authorization não vem
bearer = HTTPBearer(auto_error=False)


async def usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> Usuario:
    """Identifica quem faz o pedido. Aceita conta pendente: serve às rotas que ela pode usar."""
    if credenciais is None:
        nao_autenticado()
    sessao = ler_sessao(credenciais.credentials)
    if sessao is None:
        nao_autenticado()
    usuario_id, versao_sessao = sessao

    # O perfil e a situação vêm sempre do banco, não do token. Uma versão de sessão diferente da
    # do banco quer dizer que a senha mudou ou que a pessoa encerrou as sessões (BE-S5-07).
    usuario = await db.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo or usuario.versao_sessao != versao_sessao:
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


def _exigir_mentor_ativado(usuario: Usuario) -> None:
    if not usuario.mentor_ativado_em or not usuario.mentor_perfil_concluido_em:
        raise HTTPException(403, "Mentor pendente: conclua o perfil e aceite os termos (RN33).")


async def usuario_ativo(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    """Exige RN33 concluída para mentor e comprovante aprovado para participante pendente."""
    if usuario.papel == PapelUsuario.MENTOR:
        _exigir_mentor_ativado(usuario)
    elif usuario.situacao_conta == SituacaoConta.PENDENTE:
        conta_pendente()
    return usuario


async def usuario_convidado(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    """Para quem responde a um convite e aceita os termos (BE-S5-02). Quem se cadastrou pelo link do
    convite ainda aguarda a conferência do comprovante (RN25), mas precisa aceitar a participação e
    os termos com a própria conta: a conta pendente passa aqui. O vínculo comprovado continua
    pesando na homologação da equipe (RF23), não neste aceite. Mentor segue a RN33."""
    if usuario.papel == PapelUsuario.MENTOR:
        _exigir_mentor_ativado(usuario)
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
