from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FuncaoMembro, PapelUsuario, StatusConvite, StatusHackathon
from app.controllers.convite import (
    contar_pendentes,
    criar_convite,
    get_convite_by_id,
    listar_convites_da_equipe,
    listar_pendentes_do_email,
)
from app.controllers.equipe import get_equipe_by_id, get_hackathon_by_id
from app.controllers.membro_equipe import (
    adicionar_membro,
    contar_membros,
    get_membro,
    get_membro_no_hackathon,
)
from app.controllers.termo import registrar_aceites
from app.controllers.usuario import get_usuario_by_email
from app.exceptions.convite import (
    apenas_integrante_da_equipe,
    apenas_lider_da_equipe,
    convite_ja_respondido,
    convite_nao_encontrado,
    equipe_nao_encontrada,
    equipe_sem_vagas,
    fora_do_periodo_de_inscricao,
    ja_e_integrante,
    ja_esta_em_outra_equipe,
)
from app.exceptions.db import erro_de_integridade_sql
from app.models import Convite, Equipe, Hackathon, MembroEquipe, Usuario
from app.schemas.convite import ConviteEnvio, ConviteRecebidoResponse
from app.services.termo import validar_termos_aceitos


def _agora_utc() -> datetime:
    """UTC sem fuso: as colunas `timestamp` do banco guardam UTC sem informação de fuso."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _equipe_e_hackathon(
    db: AsyncSession, equipe_id: UUID, *, para_atualizar: bool = False
) -> tuple[Equipe, Hackathon]:
    equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=para_atualizar)
    if equipe is None:
        equipe_nao_encontrada()
    hackathon = await get_hackathon_by_id(db, equipe.hackathon_id)
    return equipe, hackathon


def _exigir_inscricoes_abertas(hackathon: Hackathon) -> None:
    """RN06: convites só valem durante as inscrições."""
    if hackathon.status != StatusHackathon.INSCRICOES:
        fora_do_periodo_de_inscricao()


async def _exigir_lider(db: AsyncSession, equipe_id: UUID, usuario: Usuario) -> None:
    """Líder técnico = `membros_equipe.funcao = LIDER`. DEV passa em tudo (exceção do time)."""
    if usuario.papel == PapelUsuario.DEV:
        return
    membro = await get_membro(db, equipe_id, usuario.id)
    if membro is None or membro.funcao != FuncaoMembro.LIDER:
        apenas_lider_da_equipe()


async def enviar_convite(
    db: AsyncSession, lider: Usuario, equipe_id: UUID, dados: ConviteEnvio
) -> Convite:
    """O líder convida por nome e e-mail (RF18). O total de integrantes mais convites pendentes
    não passa do máximo do hackathon. O envio do e-mail ainda não existe: o convite fica
    registrado e aparece no painel de quem tem conta com aquele e-mail."""
    equipe, hackathon = await _equipe_e_hackathon(db, equipe_id, para_atualizar=True)
    await _exigir_lider(db, equipe.id, lider)
    _exigir_inscricoes_abertas(hackathon)

    email = str(dados.email).lower()
    convidado = await get_usuario_by_email(db, email)
    if convidado is not None and await get_membro(db, equipe.id, convidado.id) is not None:
        ja_e_integrante()

    ocupadas = await contar_membros(db, equipe.id) + await contar_pendentes(db, equipe.id)
    if ocupadas >= hackathon.max_integrantes:
        equipe_sem_vagas(hackathon.max_integrantes)

    convite = await criar_convite(
        db,
        Convite(
            equipe_id=equipe.id,
            nome=dados.nome,
            email=email,
            usuario_id=convidado.id if convidado else None,
            convidado_por=lider.id,
        ),
    )
    await db.commit()
    await db.refresh(convite)
    return convite


async def listar_convites(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> list[Convite]:
    equipe, _ = await _equipe_e_hackathon(db, equipe_id)
    if usuario.papel != PapelUsuario.DEV and await get_membro(db, equipe.id, usuario.id) is None:
        apenas_integrante_da_equipe()
    return await listar_convites_da_equipe(db, equipe.id)


async def listar_convites_recebidos(
    db: AsyncSession, usuario: Usuario
) -> list[ConviteRecebidoResponse]:
    """Convites pendentes dirigidos ao e-mail de quem está logado (RF19)."""
    recebidos = await listar_pendentes_do_email(db, usuario.email)
    return [
        ConviteRecebidoResponse(
            id=convite.id,
            equipe_id=equipe.id,
            equipe_nome=equipe.nome,
            hackathon_id=equipe.hackathon_id,
            nome=convite.nome,
            status=convite.status,
            enviado_em=convite.enviado_em,
        )
        for convite, equipe in recebidos
    ]


async def _convite_pendente_do_destinatario(
    db: AsyncSession, usuario: Usuario, convite_id: UUID
) -> Convite:
    """Trava o convite e confere que é dirigido a quem responde. Para os demais, o convite
    'não existe': a resposta não revela convites de outras pessoas."""
    convite = await get_convite_by_id(db, convite_id, para_atualizar=True)
    if convite is None or convite.email.lower() != usuario.email.lower():
        convite_nao_encontrado()
    if convite.status != StatusConvite.PENDENTE:
        convite_ja_respondido()
    return convite


async def aceitar_convite(
    db: AsyncSession, usuario: Usuario, convite_id: UUID, termos_ids: list[UUID]
) -> Convite:
    """Aceita o convite e entra na equipe (RF19), registrando o aceite do regulamento e do
    termo de consentimento vigentes (RF20). Tudo em uma transação: se algo falhar, nada vale."""
    convite = await _convite_pendente_do_destinatario(db, usuario, convite_id)
    # Trava a equipe para que aceites simultâneos não passem do máximo de integrantes
    equipe, hackathon = await _equipe_e_hackathon(db, convite.equipe_id, para_atualizar=True)
    _exigir_inscricoes_abertas(hackathon)

    if await get_membro_no_hackathon(db, hackathon.id, usuario.id) is not None:
        ja_esta_em_outra_equipe()
    if await contar_membros(db, equipe.id) >= hackathon.max_integrantes:
        equipe_sem_vagas(hackathon.max_integrantes)

    ids_aceitos = await validar_termos_aceitos(db, hackathon.id, termos_ids)
    await registrar_aceites(db, usuario.id, ids_aceitos)

    adicionar_membro(
        db, MembroEquipe(equipe_id=equipe.id, usuario_id=usuario.id, hackathon_id=hackathon.id)
    )
    convite.status = StatusConvite.ACEITO
    convite.usuario_id = usuario.id
    convite.respondido_em = _agora_utc()
    db.add(convite)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        # Duas respostas simultâneas da mesma pessoa: a restrição única do banco decide
        if "uq_membros_equipe_hackathon_usuario" in str(error.orig):
            ja_esta_em_outra_equipe()
        erro_de_integridade_sql(error)
    await db.refresh(convite)
    return convite


async def recusar_convite(db: AsyncSession, usuario: Usuario, convite_id: UUID) -> Convite:
    """Recusar libera a vaga (índice único só considera convites pendentes e aceitos)."""
    convite = await _convite_pendente_do_destinatario(db, usuario, convite_id)
    _, hackathon = await _equipe_e_hackathon(db, convite.equipe_id)
    _exigir_inscricoes_abertas(hackathon)

    convite.status = StatusConvite.RECUSADO
    convite.usuario_id = usuario.id
    convite.respondido_em = _agora_utc()
    db.add(convite)
    await db.commit()
    await db.refresh(convite)
    return convite


async def cancelar_convite(db: AsyncSession, lider: Usuario, convite_id: UUID) -> Convite:
    """O líder retira um convite que ainda não foi respondido; a vaga volta a ficar livre."""
    convite = await get_convite_by_id(db, convite_id, para_atualizar=True)
    if convite is None:
        convite_nao_encontrado()
    await _exigir_lider(db, convite.equipe_id, lider)
    if convite.status != StatusConvite.PENDENTE:
        convite_ja_respondido()

    convite.status = StatusConvite.CANCELADO
    db.add(convite)
    await db.commit()
    await db.refresh(convite)
    return convite
