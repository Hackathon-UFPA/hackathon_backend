from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FuncaoMembro, PapelUsuario, SituacaoEquipe, StatusHackathon
from app.controllers.equipe import (
    atualizar_equipe,
    criar_equipe,
    get_equipe_by_id,
    get_hackathon_by_id,
    listar_equipes_do_usuario,
)
from app.controllers.membro_equipe import adicionar_membro, get_membro, get_membro_no_hackathon
from app.exceptions.convite import (
    apenas_lider_da_equipe,
    equipe_nao_encontrada,
    fora_do_periodo_de_inscricao,
    hackathon_nao_encontrado,
    ja_esta_em_outra_equipe,
)
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.equipe import consulta_apenas_por_integrante, equipe_nao_editavel
from app.models import Equipe, MembroEquipe, Usuario
from app.schemas.equipe import EquipeCreate, EquipeUpdate


async def criar(db: AsyncSession, usuario: Usuario, dados: EquipeCreate) -> Equipe:
    hackathon = await get_hackathon_by_id(db, dados.hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    # Mesmo critério do fluxo de convites: o status controla as inscrições (RN06).
    if hackathon.status != StatusHackathon.INSCRICOES:
        fora_do_periodo_de_inscricao()
    if await get_membro_no_hackathon(db, hackathon.id, usuario.id) is not None:
        ja_esta_em_outra_equipe()

    # O mínimo de integrantes será validado na conclusão da inscrição, não na formação.
    equipe = Equipe(**dados.model_dump(), criado_em=datetime.now(UTC))
    try:
        await criar_equipe(db, equipe)
        adicionar_membro(
            db,
            MembroEquipe(
                equipe_id=equipe.id,
                usuario_id=usuario.id,
                hackathon_id=hackathon.id,
                funcao=FuncaoMembro.LIDER,
            ),
        )
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        # Também cobre a disputa com outra criação ou aceite de convite (RN02).
        if "uq_membros_equipe_hackathon_usuario" in str(error.orig):
            ja_esta_em_outra_equipe()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(equipe)
    return equipe


async def listar_minhas(db: AsyncSession, usuario: Usuario) -> list[Equipe]:
    # Inclusive DEV recebe apenas as equipes em que participa nesta listagem.
    return await listar_equipes_do_usuario(db, usuario.id)


async def consultar(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> Equipe:
    equipe = await get_equipe_by_id(db, equipe_id)
    if equipe is None:
        equipe_nao_encontrada()
    if usuario.papel != PapelUsuario.DEV and await get_membro(db, equipe.id, usuario.id) is None:
        consulta_apenas_por_integrante()
    return equipe


async def editar(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, dados: EquipeUpdate
) -> Equipe:
    equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=True)
    if equipe is None:
        equipe_nao_encontrada()
    if usuario.papel != PapelUsuario.DEV:
        membro = await get_membro(db, equipe.id, usuario.id)
        if membro is None or membro.funcao != FuncaoMembro.LIDER:
            apenas_lider_da_equipe()
    hackathon = await get_hackathon_by_id(db, equipe.hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    if hackathon.status != StatusHackathon.INSCRICOES:
        fora_do_periodo_de_inscricao()
    if equipe.situacao != SituacaoEquipe.EM_FORMACAO:
        equipe_nao_editavel()

    try:
        if dados.model_fields_set:
            equipe.atualizado_em = datetime.now(UTC)
            await atualizar_equipe(db, equipe, dados)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(equipe)
    return equipe
