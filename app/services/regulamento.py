"""Regulamento e termos com versões (RF11, RN05, BE-S5-12).

Ciclo de uma versão: nasce **rascunho** (editável e excluível, invisível ao público), é
**publicada** (passa a vigente e a versão vigente anterior do mesmo tipo deixa de ser) e, daí em
diante, **não muda mais**: uma correção vira uma versão nova. Quem aceitou uma versão (RF20) mantém
o aceite ligado a ela, e a nova versão passa a exigir novo aceite."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoTermo
from app.controllers.termo import get_termo, get_termo_vigente, listar_termos
from app.exceptions.conteudo import conflito_de_conteudo, conteudo_invalido, item_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.models import Termo
from app.schemas.conteudo import TermoRascunhoCreate, TermoRascunhoUpdate
from app.services.conteudo import edicao


async def criar_rascunho(db: AsyncSession, hackathon_id: UUID, dados: TermoRascunhoCreate) -> Termo:
    await edicao(db, hackathon_id)
    termo = Termo(hackathon_id=hackathon_id, vigente=False, rascunho=True, **dados.model_dump())
    db.add(termo)
    try:
        await db.flush()
    except IntegrityError as erro:
        await db.rollback()
        if "uq_termos_hackathon_tipo_versao" in str(erro.orig):
            conflito_de_conteudo(
                "Já existe uma versão com este número para este tipo de documento."
            )
        erro_de_integridade_sql(erro)
    # O banco preenche `publicado_em` com a hora atual; rascunho ainda não foi publicado
    termo.publicado_em = None
    db.add(termo)
    await db.commit()
    await db.refresh(termo)
    return termo


async def listar(
    db: AsyncSession,
    hackathon_id: UUID,
    *,
    tipo: TipoTermo | None,
    rascunho: bool | None,
    limite: int,
    deslocamento: int,
) -> list[Termo]:
    await edicao(db, hackathon_id)
    return await listar_termos(
        db,
        hackathon_id,
        tipo=tipo,
        rascunho=rascunho,
        limite=limite,
        deslocamento=deslocamento,
    )


async def _rascunho_para_alterar(db: AsyncSession, hackathon_id: UUID, termo_id: UUID) -> Termo:
    await edicao(db, hackathon_id)
    termo = await get_termo(db, hackathon_id, termo_id, bloquear=True)
    if termo is None:
        item_nao_encontrado("Versão")
    if not termo.rascunho:
        conflito_de_conteudo(
            "Uma versão publicada não muda mais (RN05): crie uma nova versão para corrigi-la."
        )
    return termo


async def editar_rascunho(
    db: AsyncSession, hackathon_id: UUID, termo_id: UUID, dados: TermoRascunhoUpdate
) -> Termo:
    termo = await _rascunho_para_alterar(db, hackathon_id, termo_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(termo, campo, valor)
    if termo.conteudo is None and termo.url is None:
        conteudo_invalido("Informe o conteudo ou a url do documento.")
    db.add(termo)
    await db.commit()
    await db.refresh(termo)
    return termo


async def excluir_rascunho(db: AsyncSession, hackathon_id: UUID, termo_id: UUID) -> None:
    termo = await _rascunho_para_alterar(db, hackathon_id, termo_id)
    await db.delete(termo)
    await db.commit()


async def publicar(db: AsyncSession, hackathon_id: UUID, termo_id: UUID) -> Termo:
    """Torna a versão vigente e aposenta a anterior do mesmo tipo, na mesma transação. A edição
    fica travada: duas publicações simultâneas se enfileiram, e a última vence."""
    await edicao(db, hackathon_id, travar=True)
    termo = await get_termo(db, hackathon_id, termo_id, bloquear=True)
    if termo is None:
        item_nao_encontrado("Versão")
    if termo.vigente:
        return termo
    if not termo.rascunho:
        conflito_de_conteudo(
            "Esta versão já foi substituída por outra: crie uma nova versão para publicar."
        )
    anterior = await get_termo_vigente(db, hackathon_id, termo.tipo)
    if anterior is not None:
        anterior.vigente = False
        db.add(anterior)
        # O índice único de vigente exige que a antiga saia antes de a nova entrar
        await db.flush()
    termo.rascunho = False
    termo.vigente = True
    termo.publicado_em = datetime.now(UTC)
    db.add(termo)
    await db.commit()
    await db.refresh(termo)
    return termo
