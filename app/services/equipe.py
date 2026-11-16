from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import CategoriaEquipe, FuncaoMembro, PapelUsuario, SituacaoEquipe
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
from app.services.composicao import validar_composicao
from app.services.convite import convidar
from app.services.somente_leitura import exigir_equipe_editavel
from app.validations.categoria_equipe import exigir_categoria_permitida, resolver_tipo
from app.validations.inscricao import inscricoes_abertas


async def criar(db: AsyncSession, usuario: Usuario, dados: EquipeCreate) -> Equipe:
    hackathon = await get_hackathon_by_id(db, dados.hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    if not inscricoes_abertas(hackathon):
        fora_do_periodo_de_inscricao()
    if await get_membro_no_hackathon(db, hackathon.id, usuario.id) is not None:
        ja_esta_em_outra_equipe()

    # Sem `categoria`, vale ESTUDANTES: é o comportamento de antes da decisão de 05/11
    categoria = dados.categoria or CategoriaEquipe.ESTUDANTES
    if dados.integrantes is not None:
        # Composição informada de uma vez: tamanho (RN01), categoria, tipos e e-mails conferidos
        # antes de gravar qualquer coisa. Sem ela, o mínimo só vale na conclusão da inscrição.
        tipo_lider, indicados = validar_composicao(
            hackathon,
            categoria,
            tipo_lider=dados.tipo_lider,
            email_lider=usuario.email,
            integrantes=dados.integrantes,
        )
    else:
        exigir_categoria_permitida(hackathon, categoria)
        tipo_lider, indicados = resolver_tipo(categoria, dados.tipo_lider, "o líder"), []

    equipe = Equipe(
        hackathon_id=hackathon.id,
        nome=dados.nome,
        categoria=categoria,
        criado_em=datetime.now(UTC),
    )
    try:
        await criar_equipe(db, equipe)
        adicionar_membro(
            db,
            MembroEquipe(
                equipe_id=equipe.id,
                usuario_id=usuario.id,
                hackathon_id=hackathon.id,
                funcao=FuncaoMembro.LIDER,
                tipo_integrante=tipo_lider,
            ),
        )
        # Descarrega o vínculo do líder já aqui: a violação de unicidade (RN02) tem de aparecer
        # neste bloco, como 409, e não dentro da criação de um convite
        await db.flush()
        for indicado in indicados:
            await convidar(db, equipe, usuario, indicado.nome, indicado.email, indicado.tipo)
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
    await exigir_equipe_editavel(db, equipe.id)
    hackathon = await get_hackathon_by_id(db, equipe.hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    if not inscricoes_abertas(hackathon):
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
