from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, SituacaoEquipe, StatusHackathon, TipoMarcoMentoria
from app.controllers import mentoria as controller
from app.controllers.atribuicao_mentor import equipe_aprovada, vigente
from app.controllers.conteudo import get_item, listar_itens
from app.controllers.equipe import get_equipe_by_id, get_hackathon_id_da_equipe
from app.controllers.hackathon import get_hackathon_compartilhado
from app.controllers.membro_equipe import get_membro, get_membro_no_hackathon
from app.exceptions.atribuicao_mentor import conflito_mentoria
from app.exceptions.auth import acesso_negado
from app.exceptions.conteudo import item_nao_encontrado
from app.exceptions.convite import equipe_nao_encontrada, hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.models import EntregaMentoria, Equipe, Hackathon, MarcoMentoria, Usuario
from app.schemas.mentoria import EntregaMentoriaCreate, MarcoMentoriaCreate, MarcoMentoriaUpdate
from app.security.organizacao import mesma_organizacao
from app.services.conteudo import agora_utc, edicao
from app.services.convite import exigir_lider
from app.services.hackathon import obter_acessivel
from app.validations.inscricao import como_utc

GESTORES_MENTORIA = (PapelUsuario.COMITE_CIENTIFICO, PapelUsuario.ORGANIZADOR)


def _gestor_da_edicao(usuario: Usuario, hackathon: Hackathon) -> bool:
    return usuario.papel in GESTORES_MENTORIA and mesma_organizacao(
        usuario, hackathon.organizacao_id
    )


def _inicio_mentoria(hackathon: Hackathon) -> datetime | None:
    datas = (hackathon.data_inicio, hackathon.propostas_fim, hackathon.treinamento_concluido_em)
    return max((como_utc(data) for data in datas if data is not None), default=None)


def _validar_prazo_edicao(hackathon: Hackathon, data_limite: datetime) -> None:
    inicio = _inicio_mentoria(hackathon)
    if inicio is not None and data_limite < inicio:
        conflito_mentoria("O prazo do marco é anterior ao início possível da mentoria da edição.")
    if hackathon.data_fim is not None and data_limite > como_utc(hackathon.data_fim):
        conflito_mentoria("O prazo do marco é posterior ao fim da edição.")


async def _validar_calendario(db: AsyncSession, hackathon: Hackathon, marco: MarcoMentoria) -> None:
    _validar_prazo_edicao(hackathon, marco.data_limite)
    final = await controller.ultimo_marco(db, hackathon.id, TipoMarcoMentoria.FINAL, marco.id)
    posicao = (marco.data_limite, marco.ordem)
    if marco.tipo == TipoMarcoMentoria.FINAL:
        if final is not None:
            conflito_mentoria("A edição já possui um marco de entrega final.")
        parcial = await controller.ultimo_marco(
            db, hackathon.id, TipoMarcoMentoria.PARCIAL, marco.id
        )
        if parcial is not None and posicao <= (parcial.data_limite, parcial.ordem):
            conflito_mentoria("O marco final deve vir após todos os marcos parciais.")
    elif final is not None and posicao >= (final.data_limite, final.ordem):
        conflito_mentoria("Um marco parcial deve vir antes do marco final.")


async def _confirmar(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as erro:
        await db.rollback()
        mensagem = str(erro.orig)
        if "uq_marcos_mentoria_final" in mensagem:
            conflito_mentoria("A edição já possui um marco de entrega final.")
        if "uq_entregas_mentoria_marco_equipe" in mensagem:
            conflito_mentoria("A equipe já registrou uma entrega para este marco.")
        if "fk_entregas_mentoria_marco_edicao" in mensagem:
            conflito_mentoria("A operação conflita com entregas vinculadas ao marco.")
        erro_de_integridade_sql(erro)


async def _marco(db: AsyncSession, hackathon_id: UUID, marco_id: UUID) -> MarcoMentoria:
    marco = await get_item(db, MarcoMentoria, hackathon_id, marco_id)
    if marco is None:
        item_nao_encontrado("Marco")
    return marco


async def criar_marco(
    db: AsyncSession, hackathon_id: UUID, dados: MarcoMentoriaCreate
) -> MarcoMentoria:
    # As mudanças de calendário se serializam na edição. Envios usam a mesma trava em FOR SHARE.
    hackathon = await edicao(db, hackathon_id, travar=True)
    marco = MarcoMentoria(hackathon_id=hackathon.id, **dados.model_dump())
    await _validar_calendario(db, hackathon, marco)
    db.add(marco)
    await _confirmar(db)
    return marco


async def editar_marco(
    db: AsyncSession, hackathon_id: UUID, marco_id: UUID, dados: MarcoMentoriaUpdate
) -> MarcoMentoria:
    hackathon = await edicao(db, hackathon_id, travar=True)
    marco = await _marco(db, hackathon_id, marco_id)
    valores = dados.model_dump(exclude_unset=True)
    if valores:
        if valores.get("tipo", marco.tipo) != marco.tipo and await controller.marco_tem_entregas(
            db, marco.id
        ):
            conflito_mentoria("O tipo de um marco com entregas registradas não pode mudar.")
        marco.sqlmodel_update(valores)
        with db.no_autoflush:
            await _validar_calendario(db, hackathon, marco)
        marco.atualizado_em = agora_utc()
    await _confirmar(db)
    return marco


async def excluir_marco(db: AsyncSession, hackathon_id: UUID, marco_id: UUID) -> None:
    await edicao(db, hackathon_id, travar=True)
    marco = await _marco(db, hackathon_id, marco_id)
    if await controller.marco_tem_entregas(db, marco.id):
        conflito_mentoria("Um marco com entregas registradas não pode ser excluído.")
    await db.delete(marco)
    await _confirmar(db)


async def consultar_marco(db: AsyncSession, hackathon_id: UUID, marco_id: UUID) -> MarcoMentoria:
    await edicao(db, hackathon_id)
    return await _marco(db, hackathon_id, marco_id)


async def _equipe_autorizada(db: AsyncSession, equipe: Equipe) -> bool:
    return equipe.situacao == SituacaoEquipe.HOMOLOGADA and await equipe_aprovada(
        db, equipe.id, equipe.hackathon_id
    )


async def _pode_ver_calendario(db: AsyncSession, usuario: Usuario, hackathon: Hackathon) -> bool:
    if usuario.papel == PapelUsuario.DEV or _gestor_da_edicao(usuario, hackathon):
        return True
    if usuario.papel == PapelUsuario.MENTOR:
        return mesma_organizacao(usuario, hackathon.organizacao_id) and (
            await controller.mentor_acompanha_edicao(db, usuario.id, hackathon.id)
        )
    if usuario.papel == PapelUsuario.PARTICIPANTE:
        membro = await get_membro_no_hackathon(db, hackathon.id, usuario.id)
        if membro is not None:
            equipe = await get_equipe_by_id(db, membro.equipe_id)
            return equipe is not None and await _equipe_autorizada(db, equipe)
    return False


async def listar_marcos(
    db: AsyncSession, usuario: Usuario, hackathon_id: UUID, limite: int, deslocamento: int
) -> list[MarcoMentoria]:
    hackathon = await obter_acessivel(db, hackathon_id, usuario)
    if not await _pode_ver_calendario(db, usuario, hackathon):
        acesso_negado()
    return await listar_itens(
        db,
        MarcoMentoria,
        hackathon.id,
        ordem=controller.ORDEM_CALENDARIO,
        limite=limite,
        deslocamento=deslocamento,
    )


async def registrar_entrega(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, dados: EntregaMentoriaCreate
) -> EntregaMentoria:
    # A edição vem antes da equipe, como no envio de proposta e na homologação de resultado.
    hackathon_id = await get_hackathon_id_da_equipe(db, equipe_id)
    if hackathon_id is None:
        equipe_nao_encontrada()
    hackathon = await get_hackathon_compartilhado(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=True)
    if equipe is None:
        equipe_nao_encontrada()
    await exigir_lider(db, equipe.id, usuario)
    if not await _equipe_autorizada(db, equipe):
        conflito_mentoria("A equipe precisa estar homologada e ter proposta aprovada.")
    if (
        hackathon.status
        in (StatusHackathon.RASCUNHO, StatusHackathon.FINALIZADO, StatusHackathon.CANCELADO)
        or hackathon.treinamento_concluido_em is None
    ):
        conflito_mentoria("A mentoria exige treinamento concluído em uma edição aberta.")
    marco = await _marco(db, equipe.hackathon_id, dados.marco_id)
    if marco.tipo != TipoMarcoMentoria.PARCIAL:
        conflito_mentoria("Este endpoint aceita apenas marcos parciais.")
    _validar_prazo_edicao(hackathon, marco.data_limite)
    agora = agora_utc()
    inicio = _inicio_mentoria(hackathon)
    if inicio is not None and agora < inicio:
        conflito_mentoria("O período de mentoria ainda não começou.")
    if agora > marco.data_limite:
        conflito_mentoria("O prazo de entrega deste marco foi encerrado.")
    entrega = EntregaMentoria(
        marco_id=marco.id,
        equipe_id=equipe.id,
        hackathon_id=equipe.hackathon_id,
        enviado_por=usuario.id,
        enviado_em=agora,
        data_limite_no_envio=marco.data_limite,
        descricao=dados.descricao,
        referencias=dados.referencias,
    )
    db.add(entrega)
    await _confirmar(db)
    return entrega


async def _autorizar_consulta_entregas(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> None:
    equipe = await get_equipe_by_id(db, equipe_id)
    if equipe is None:
        equipe_nao_encontrada()
    hackathon = await obter_acessivel(db, equipe.hackathon_id, usuario)
    if usuario.papel == PapelUsuario.DEV or _gestor_da_edicao(usuario, hackathon):
        return
    if usuario.papel == PapelUsuario.MENTOR and mesma_organizacao(
        usuario, hackathon.organizacao_id
    ):
        atribuicao = await vigente(db, equipe.id)
        if atribuicao is not None and atribuicao.mentor_id == usuario.id:
            return
    if usuario.papel == PapelUsuario.PARTICIPANTE:
        if await get_membro(db, equipe.id, usuario.id) is not None:
            return
    acesso_negado()


async def listar_entregas(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, limite: int, deslocamento: int
) -> list[EntregaMentoria]:
    await _autorizar_consulta_entregas(db, usuario, equipe_id)
    return await controller.listar_entregas(db, equipe_id, limite, deslocamento)


async def consultar_entrega(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, entrega_id: UUID
) -> EntregaMentoria:
    await _autorizar_consulta_entregas(db, usuario, equipe_id)
    entrega = await controller.get_entrega(db, equipe_id, entrega_id)
    if entrega is None:
        item_nao_encontrado("Registro de entrega")
    return entrega
