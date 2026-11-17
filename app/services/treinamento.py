"""Agenda e materiais do treinamento (RF35, BE-S5-12).

Cada sessão tem data, horário e local ou link, e pode ter materiais, sempre como links (RNF20).
Só a organização vê tudo; as equipes aprovadas veem apenas o que foi publicado. RF36 (presença no
treinamento) continua **removido**: não há registro de participação. O aviso às equipes quando algo
muda depende da Q09 e não foi implementado."""

from uuid import UUID

from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario
from app.controllers.atribuicao_mentor import equipe_aprovada
from app.controllers.conteudo import (
    get_item,
    get_material,
    listar_itens,
    listar_materiais,
    proxima_ordem_material,
    remover_item,
    salvar_item,
)
from app.controllers.membro_equipe import get_membro_no_hackathon
from app.exceptions.conteudo import (
    acesso_ao_treinamento_negado,
    conteudo_invalido,
    item_nao_encontrado,
)
from app.models import Hackathon, MaterialTreinamento, SessaoTreinamento, Usuario
from app.schemas.conteudo import (
    MaterialCreate,
    SessaoCreate,
    SessaoResponse,
    SessaoUpdate,
)
from app.security.organizacao import mesma_organizacao
from app.security.permissoes import PERFIS_QUE_ACOMPANHAM_TREINAMENTO
from app.services.conteudo import agora_utc, edicao
from app.validations.inscricao import como_utc


def _validar(sessao: SessaoTreinamento) -> None:
    if sessao.fim is not None and como_utc(sessao.fim) < como_utc(sessao.inicio):
        conteudo_invalido("fim não pode ser antes de inicio.")
    if sessao.local is None and sessao.link_url is None:
        conteudo_invalido("Informe o local ou o link da sessão.")


def _resposta(sessao: SessaoTreinamento, materiais: list[MaterialTreinamento]) -> SessaoResponse:
    return SessaoResponse(
        id=sessao.id,
        hackathon_id=sessao.hackathon_id,
        titulo=sessao.titulo,
        descricao=sessao.descricao,
        inicio=sessao.inicio,
        fim=sessao.fim,
        local=sessao.local,
        link_url=sessao.link_url,
        publicado=sessao.publicado,
        materiais=materiais,
        atualizado_em=sessao.atualizado_em,
    )


async def _com_materiais(
    db: AsyncSession, sessoes: list[SessaoTreinamento]
) -> list[SessaoResponse]:
    materiais = await listar_materiais(db, [s.id for s in sessoes])
    return [_resposta(s, materiais.get(s.id, [])) for s in sessoes]


async def _sessao(
    db: AsyncSession, hackathon_id: UUID, sessao_id: UUID, *, bloquear: bool = False
) -> SessaoTreinamento:
    sessao = await get_item(db, SessaoTreinamento, hackathon_id, sessao_id, bloquear=bloquear)
    if sessao is None:
        item_nao_encontrado("Sessão")
    return sessao


async def criar_sessao(db: AsyncSession, hackathon_id: UUID, dados: SessaoCreate) -> SessaoResponse:
    await edicao(db, hackathon_id)
    sessao = SessaoTreinamento(hackathon_id=hackathon_id, **dados.model_dump())
    await salvar_item(db, sessao)
    await db.commit()
    await db.refresh(sessao)
    return _resposta(sessao, [])


async def listar_sessoes_admin(
    db: AsyncSession,
    hackathon_id: UUID,
    *,
    publicado: bool | None,
    limite: int,
    deslocamento: int,
) -> list[SessaoResponse]:
    await edicao(db, hackathon_id)
    filtros = () if publicado is None else (SessaoTreinamento.publicado == publicado,)
    sessoes = await listar_itens(
        db,
        SessaoTreinamento,
        hackathon_id,
        filtros=filtros,
        ordem=(SessaoTreinamento.inicio, SessaoTreinamento.titulo, SessaoTreinamento.id),
        limite=limite,
        deslocamento=deslocamento,
    )
    return await _com_materiais(db, sessoes)


async def editar_sessao(
    db: AsyncSession, hackathon_id: UUID, sessao_id: UUID, dados: SessaoUpdate
) -> SessaoResponse:
    await edicao(db, hackathon_id)
    sessao = await _sessao(db, hackathon_id, sessao_id, bloquear=True)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(sessao, campo, valor)
    sessao.atualizado_em = agora_utc()
    _validar(sessao)
    await salvar_item(db, sessao)
    await db.commit()
    await db.refresh(sessao)
    return (await _com_materiais(db, [sessao]))[0]


async def excluir_sessao(db: AsyncSession, hackathon_id: UUID, sessao_id: UUID) -> None:
    """Os materiais da sessão saem junto (ON DELETE CASCADE)."""
    await edicao(db, hackathon_id)
    sessao = await _sessao(db, hackathon_id, sessao_id, bloquear=True)
    await remover_item(db, sessao)
    await db.commit()


async def adicionar_material(
    db: AsyncSession, hackathon_id: UUID, sessao_id: UUID, dados: MaterialCreate
) -> MaterialTreinamento:
    await edicao(db, hackathon_id)
    # Travar a sessão serializa materiais simultâneos e dá a cada um uma posição própria
    sessao = await _sessao(db, hackathon_id, sessao_id, bloquear=True)
    material = MaterialTreinamento(
        sessao_id=sessao.id,
        ordem=await proxima_ordem_material(db, sessao.id),
        **dados.model_dump(),
    )
    sessao.atualizado_em = agora_utc()
    db.add(sessao)
    await salvar_item(db, material)
    await db.commit()
    await db.refresh(material)
    return material


async def remover_material(
    db: AsyncSession, hackathon_id: UUID, sessao_id: UUID, material_id: UUID
) -> None:
    await edicao(db, hackathon_id)
    sessao = await _sessao(db, hackathon_id, sessao_id, bloquear=True)
    material = await get_material(db, sessao.id, material_id)
    if material is None:
        item_nao_encontrado("Material")
    sessao.atualizado_em = agora_utc()
    db.add(sessao)
    await remover_item(db, material)
    await db.commit()


async def pode_ver(db: AsyncSession, usuario: Usuario, hackathon_id: UUID) -> bool:
    """Equipe interna da organização dona (e DEV) sempre; os demais, só integrantes de equipe
    aprovada na edição."""
    if usuario.papel == PapelUsuario.DEV:
        return True
    if usuario.papel in PERFIS_QUE_ACOMPANHAM_TREINAMENTO:
        hackathon = await db.get(Hackathon, hackathon_id)
        return hackathon is not None and mesma_organizacao(usuario, hackathon.organizacao_id)
    membro = await get_membro_no_hackathon(db, hackathon_id, usuario.id)
    return membro is not None and await equipe_aprovada(db, membro.equipe_id, hackathon_id)


async def treinamento_da_edicao(
    db: AsyncSession, usuario: Usuario, hackathon_id: UUID
) -> list[SessaoResponse]:
    """Sessões publicadas, com materiais, em ordem cronológica (RF35)."""
    await edicao(db, hackathon_id)
    if not await pode_ver(db, usuario, hackathon_id):
        acesso_ao_treinamento_negado()
    sessoes = await listar_itens(
        db,
        SessaoTreinamento,
        hackathon_id,
        filtros=(col(SessaoTreinamento.publicado).is_(True),),
        ordem=(SessaoTreinamento.inicio, SessaoTreinamento.titulo, SessaoTreinamento.id),
    )
    return await _com_materiais(db, sessoes)
