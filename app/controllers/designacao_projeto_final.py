from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, SituacaoConta
from app.models import (
    AtribuicaoMentor,
    ConflitoProjetoFinal,
    DesignacaoProjetoFinal,
    Equipe,
    MembroEquipe,
    ResultadoProposta,
    Submissao,
    Usuario,
)


def _elegivel(organizacao_id: UUID | None):
    """Comitê Técnico com conta ativa da organização dona do hackathon (RF47)."""
    return (
        Usuario.papel == PapelUsuario.COMITE_TECNICO,
        col(Usuario.organizacao_id).is_not_distinct_from(organizacao_id),
        col(Usuario.ativo).is_(True),
        Usuario.situacao_conta == SituacaoConta.ATIVA,
    )


async def listar_projetos_finais(db: AsyncSession, homologacao_id: UUID) -> list[ResultadoProposta]:
    """Propostas aprovadas na homologação científica. Ordem fixa pelo id da submissão."""
    consulta = (
        select(ResultadoProposta)
        .where(
            ResultadoProposta.homologacao_id == homologacao_id,
            col(ResultadoProposta.aprovada).is_(True),
        )
        .order_by(col(ResultadoProposta.submissao_id))
    )
    return list((await db.exec(consulta)).all())


async def get_projeto_final(db: AsyncSession, submissao_id: UUID) -> ResultadoProposta | None:
    consulta = select(ResultadoProposta).where(
        ResultadoProposta.submissao_id == submissao_id,
        col(ResultadoProposta.aprovada).is_(True),
    )
    return (await db.exec(consulta)).first()


async def listar_avaliadores_tecnicos(
    db: AsyncSession, organizacao_id: UUID | None
) -> list[Usuario]:
    consulta = select(Usuario).where(*_elegivel(organizacao_id)).order_by(col(Usuario.id))
    return list((await db.exec(consulta)).all())


async def contar_tecnicos_entre(
    db: AsyncSession, avaliador_ids: list[UUID], organizacao_id: UUID | None
) -> int:
    consulta = select(func.count()).where(
        col(Usuario.id).in_(avaliador_ids), *_elegivel(organizacao_id)
    )
    return (await db.exec(consulta)).one()


async def get_avaliador_tecnico(
    db: AsyncSession, avaliador_id: UUID, organizacao_id: UUID | None
) -> Usuario | None:
    consulta = select(Usuario).where(
        Usuario.id == avaliador_id,
        Usuario.papel == PapelUsuario.COMITE_TECNICO,
        col(Usuario.organizacao_id).is_not_distinct_from(organizacao_id),
    )
    return (await db.exec(consulta)).first()


async def get_equipe_do_hackathon(
    db: AsyncSession, equipe_id: UUID, hackathon_id: UUID
) -> Equipe | None:
    consulta = select(Equipe).where(Equipe.id == equipe_id, Equipe.hackathon_id == hackathon_id)
    return (await db.exec(consulta)).first()


async def impedidos_por_equipe(
    db: AsyncSession, hackathon_id: UUID, equipe_ids: list[UUID]
) -> dict[UUID, set[UUID]]:
    """RN13: quem não pode avaliar o projeto de cada equipe. Integrantes, mentores (inclusive
    atribuições já encerradas) e conflitos declarados pelo Organizador."""
    impedidos: dict[UUID, set[UUID]] = defaultdict(set)
    if not equipe_ids:
        return impedidos
    membros = select(MembroEquipe.equipe_id, MembroEquipe.usuario_id).where(
        col(MembroEquipe.equipe_id).in_(equipe_ids)
    )
    mentores = select(AtribuicaoMentor.equipe_id, AtribuicaoMentor.mentor_id).where(
        col(AtribuicaoMentor.equipe_id).in_(equipe_ids)
    )
    declarados = select(ConflitoProjetoFinal.equipe_id, ConflitoProjetoFinal.avaliador_id).where(
        ConflitoProjetoFinal.hackathon_id == hackathon_id,
        col(ConflitoProjetoFinal.equipe_id).in_(equipe_ids),
    )
    for consulta in (membros, mentores, declarados):
        for equipe_id, usuario_id in (await db.exec(consulta)).all():
            impedidos[equipe_id].add(usuario_id)
    return impedidos


async def listar_vigentes_do_hackathon(
    db: AsyncSession, hackathon_id: UUID
) -> list[DesignacaoProjetoFinal]:
    consulta = (
        select(DesignacaoProjetoFinal)
        .where(
            DesignacaoProjetoFinal.hackathon_id == hackathon_id,
            col(DesignacaoProjetoFinal.removida_em).is_(None),
        )
        .order_by(col(DesignacaoProjetoFinal.atribuido_em), col(DesignacaoProjetoFinal.id))
    )
    return list((await db.exec(consulta)).all())


async def listar_vigentes_do_projeto(
    db: AsyncSession, submissao_id: UUID
) -> list[DesignacaoProjetoFinal]:
    consulta = select(DesignacaoProjetoFinal).where(
        DesignacaoProjetoFinal.submissao_id == submissao_id,
        col(DesignacaoProjetoFinal.removida_em).is_(None),
    )
    return list((await db.exec(consulta)).all())


async def existe_vigente(db: AsyncSession, equipe_id: UUID, avaliador_id: UUID) -> bool:
    consulta = select(DesignacaoProjetoFinal.id).where(
        DesignacaoProjetoFinal.equipe_id == equipe_id,
        DesignacaoProjetoFinal.avaliador_id == avaliador_id,
        col(DesignacaoProjetoFinal.removida_em).is_(None),
    )
    return (await db.exec(consulta)).first() is not None


async def carga_por_avaliador(db: AsyncSession, hackathon_id: UUID) -> dict[UUID, int]:
    consulta = (
        select(DesignacaoProjetoFinal.avaliador_id, func.count())
        .where(
            DesignacaoProjetoFinal.hackathon_id == hackathon_id,
            col(DesignacaoProjetoFinal.removida_em).is_(None),
        )
        .group_by(DesignacaoProjetoFinal.avaliador_id)
    )
    carga: dict[UUID, int] = defaultdict(int)
    for avaliador_id, total in (await db.exec(consulta)).all():
        carga[avaliador_id] = total
    return carga


async def listar_usuarios_por_id(db: AsyncSession, ids: list[UUID]) -> dict[UUID, Usuario]:
    if not ids:
        return {}
    consulta = select(Usuario).where(col(Usuario.id).in_(ids))
    return {usuario.id: usuario for usuario in (await db.exec(consulta)).all()}


def adicionar(db: AsyncSession, objeto: DesignacaoProjetoFinal | ConflitoProjetoFinal) -> None:
    db.add(objeto)


def marcar_removida(
    db: AsyncSession, designacao: DesignacaoProjetoFinal, removida_por: UUID
) -> None:
    designacao.removida_em = datetime.now(UTC)
    designacao.removida_por = removida_por
    db.add(designacao)


async def listar_conflitos(db: AsyncSession, hackathon_id: UUID) -> list[ConflitoProjetoFinal]:
    consulta = (
        select(ConflitoProjetoFinal)
        .where(ConflitoProjetoFinal.hackathon_id == hackathon_id)
        .order_by(col(ConflitoProjetoFinal.registrado_em), col(ConflitoProjetoFinal.id))
    )
    return list((await db.exec(consulta)).all())


async def get_conflito(
    db: AsyncSession, equipe_id: UUID, avaliador_id: UUID
) -> ConflitoProjetoFinal | None:
    consulta = select(ConflitoProjetoFinal).where(
        ConflitoProjetoFinal.equipe_id == equipe_id,
        ConflitoProjetoFinal.avaliador_id == avaliador_id,
    )
    return (await db.exec(consulta)).first()


async def listar_projetos_designados(db: AsyncSession, avaliador_id: UUID) -> list[Submissao]:
    consulta = (
        select(Submissao)
        .join(
            DesignacaoProjetoFinal,
            col(DesignacaoProjetoFinal.submissao_id) == col(Submissao.id),
        )
        .where(
            DesignacaoProjetoFinal.avaliador_id == avaliador_id,
            col(DesignacaoProjetoFinal.removida_em).is_(None),
        )
        .order_by(col(Submissao.enviado_em), col(Submissao.id))
    )
    return list((await db.exec(consulta)).all())


async def get_projeto_designado(
    db: AsyncSession, submissao_id: UUID, avaliador_id: UUID
) -> Submissao | None:
    consulta = (
        select(Submissao)
        .join(
            DesignacaoProjetoFinal,
            col(DesignacaoProjetoFinal.submissao_id) == col(Submissao.id),
        )
        .where(
            Submissao.id == submissao_id,
            DesignacaoProjetoFinal.avaliador_id == avaliador_id,
            col(DesignacaoProjetoFinal.removida_em).is_(None),
        )
    )
    return (await db.exec(consulta)).first()
