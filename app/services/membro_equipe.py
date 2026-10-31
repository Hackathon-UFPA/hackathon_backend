from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FuncaoMembro, PapelUsuario, SituacaoEquipe
from app.controllers.equipe import get_equipe_by_id, get_hackathon_by_id
from app.controllers.membro_equipe import (
    atualizar_membro,
    get_membro,
    listar_membros,
    remover_membro,
)
from app.exceptions.convite import (
    apenas_lider_da_equipe,
    equipe_nao_encontrada,
    fora_do_periodo_de_inscricao,
    hackathon_nao_encontrado,
)
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.equipe import equipe_nao_editavel, lider_protegido, membro_nao_encontrado
from app.models import MembroEquipe, Usuario
from app.schemas.membro_equipe import MembroEquipeUpdate
from app.services.equipe import consultar
from app.validations.inscricao import inscricoes_abertas


async def listar(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> list[MembroEquipe]:
    await consultar(db, usuario, equipe_id)
    return await listar_membros(db, equipe_id)


async def _membro_para_alteracao(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, usuario_id: UUID
) -> MembroEquipe:
    # Mesmo bloqueio do aceite/envio de convites: alterações na composição são serializadas.
    equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=True)
    if equipe is None:
        equipe_nao_encontrada()
    if usuario.papel != PapelUsuario.DEV:
        solicitante = await get_membro(db, equipe.id, usuario.id)
        if solicitante is None or solicitante.funcao != FuncaoMembro.LIDER:
            apenas_lider_da_equipe()
    hackathon = await get_hackathon_by_id(db, equipe.hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    if not inscricoes_abertas(hackathon):
        fora_do_periodo_de_inscricao()
    if equipe.situacao != SituacaoEquipe.EM_FORMACAO:
        equipe_nao_editavel()
    # A chave composta impede atingir um vínculo do mesmo usuário em outra equipe/edição.
    membro = await get_membro(db, equipe.id, usuario_id)
    if membro is None:
        membro_nao_encontrado()
    return membro


async def editar(
    db: AsyncSession,
    usuario: Usuario,
    equipe_id: UUID,
    usuario_id: UUID,
    dados: MembroEquipeUpdate,
) -> MembroEquipe:
    membro = await _membro_para_alteracao(db, usuario, equipe_id, usuario_id)
    if "funcao" in dados.model_fields_set:
        # Mesmo DEV não transfere liderança. Reenviar a mesma função é idempotente.
        if dados.funcao != membro.funcao and (
            membro.funcao == FuncaoMembro.LIDER or dados.funcao == FuncaoMembro.LIDER
        ):
            lider_protegido()
    try:
        await atualizar_membro(db, membro, dados)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(membro)
    return membro


async def remover(db: AsyncSession, usuario: Usuario, equipe_id: UUID, usuario_id: UUID) -> None:
    membro = await _membro_para_alteracao(db, usuario, equipe_id, usuario_id)
    if membro.funcao == FuncaoMembro.LIDER:
        lider_protegido()
    # Não aumenta a composição; permite reduzir até somente o líder durante a formação.
    # Convites ACEITO e aceites de termos não mudam: reconvite à mesma equipe permanece
    # bloqueado pelo índice uq_convites_equipe_email_ativo até decisão específica.
    try:
        await remover_membro(db, membro)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
