"""Isolamento entre organizações (plataforma multi-organização).

Cada hackathon pertence a uma organização, e a equipe interna dela (Organizador, Comitês e
Mentor) só gerencia as edições da própria organização. DEV continua passando em tudo.

As dependências daqui substituem `exigir_papeis` nas rotas que agem sobre um hackathon: além do
perfil, conferem que o recurso do caminho (hackathon, tema, proposta ou comprovante) é da
organização de quem pede. Recurso inexistente passa direto, para a rota responder o 404 dela.

Dados sem organização (`organizacao_id` NULL dos dois lados) contam como da mesma organização:
só existem em bancos antigos ou criados por script, nunca pelo cadastro da plataforma.
"""

from uuid import UUID

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.db.db import get_session
from app.exceptions.auth import outra_organizacao
from app.models import ComprovanteVinculo, Hackathon, Submissao, Tema, Usuario
from app.security.dependencias import exigir_papeis


async def _ler(db: AsyncSession, modelo, id_: UUID):
    """Lê sem deixar o objeto na sessão: as rotas depois travam a linha (SELECT ... FOR UPDATE)
    e precisam ver os valores lidos com a trava, não esta leitura anterior."""
    objeto = await db.get(modelo, id_)
    if objeto is not None:
        db.expunge(objeto)
    return objeto


def mesma_organizacao(usuario: Usuario, organizacao_id: UUID | None) -> bool:
    return usuario.papel == PapelUsuario.DEV or usuario.organizacao_id == organizacao_id


async def garantir_hackathon_da_organizacao(
    db: AsyncSession, usuario: Usuario, hackathon_id: UUID | None
) -> None:
    if hackathon_id is None:
        return
    hackathon = await _ler(db, Hackathon, hackathon_id)
    if hackathon is not None and not mesma_organizacao(usuario, hackathon.organizacao_id):
        outra_organizacao()


def gestor_do_hackathon(*papeis: PapelUsuario):
    """Perfis informados + o `{hackathon_id}` do caminho é da organização de quem pede."""
    base = exigir_papeis(*papeis)

    async def verificar(
        hackathon_id: UUID,
        db: AsyncSession = Depends(get_session),
        usuario: Usuario = Depends(base),
    ) -> Usuario:
        await garantir_hackathon_da_organizacao(db, usuario, hackathon_id)
        return usuario

    return verificar


def gestor_do_tema(*papeis: PapelUsuario):
    base = exigir_papeis(*papeis)

    async def verificar(
        tema_id: UUID,
        db: AsyncSession = Depends(get_session),
        usuario: Usuario = Depends(base),
    ) -> Usuario:
        tema = await _ler(db, Tema, tema_id)
        await garantir_hackathon_da_organizacao(db, usuario, tema.hackathon_id if tema else None)
        return usuario

    return verificar


def gestor_da_proposta(*papeis: PapelUsuario):
    base = exigir_papeis(*papeis)

    async def verificar(
        submissao_id: UUID,
        db: AsyncSession = Depends(get_session),
        usuario: Usuario = Depends(base),
    ) -> Usuario:
        proposta = await _ler(db, Submissao, submissao_id)
        await garantir_hackathon_da_organizacao(
            db, usuario, proposta.hackathon_id if proposta else None
        )
        return usuario

    return verificar


def conferente_do_comprovante(*papeis: PapelUsuario):
    base = exigir_papeis(*papeis)

    async def verificar(
        comprovante_id: UUID,
        db: AsyncSession = Depends(get_session),
        usuario: Usuario = Depends(base),
    ) -> Usuario:
        comprovante = await _ler(db, ComprovanteVinculo, comprovante_id)
        await garantir_hackathon_da_organizacao(
            db, usuario, comprovante.hackathon_id if comprovante else None
        )
        return usuario

    return verificar
