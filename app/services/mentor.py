import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.const.enums import PapelUsuario, SituacaoConta, TipoEmail
from app.controllers import mentor as controller
from app.controllers.termo import listar_aceites, registrar_aceites
from app.controllers.usuario import criar_usuario, get_usuario_by_email
from app.exceptions.auth import email_ja_cadastrado
from app.exceptions.mentor import convite_invalido, mentor_inelegivel, mentor_nao_encontrado
from app.models import ConviteMentor, Usuario
from app.schemas.mentor import MentorAtivacao, MentorCreate, MentorUpdate
from app.security.senha import gerar_hash
from app.services.email import enfileirar, link_front
from app.services.termo import termos_vigentes_do_hackathon, validar_termos_aceitos


def agora_utc() -> datetime:
    return datetime.now(UTC)


async def consultar(db: AsyncSession, mentor_id: UUID, *, bloquear: bool = False) -> Usuario:
    mentor = await controller.get_mentor(db, mentor_id, bloquear=bloquear)
    if mentor is None:
        mentor_nao_encontrado()
    return mentor


async def convidar(db: AsyncSession, mentor: Usuario) -> None:
    agora = agora_utc()
    await controller.invalidar_convites(db, mentor.id, agora)
    token = secrets.token_urlsafe(32)
    convite = ConviteMentor(
        usuario_id=mentor.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expira_em=agora + timedelta(minutes=settings.MENTOR_CONVITE_MINUTOS),
    )
    await controller.salvar_convite(db, convite)
    await enfileirar(
        db,
        TipoEmail.DEFINICAO_SENHA,
        destinatario_email=mentor.email,
        destinatario_nome=mentor.nome,
        usuario_id=mentor.id,
        contexto={
            "nome": mentor.nome,
            "perfil": "Mentor",
            "link": link_front(f"/mentores/ativacao#token={token}"),
        },
        chave=f"convite-mentor:{convite.id}",
    )


async def cadastrar(db: AsyncSession, dados: MentorCreate) -> Usuario:
    mentor = await criar_usuario(
        db,
        Usuario(
            **dados.model_dump(exclude={"email"}),
            email=dados.email.lower(),
            papel=PapelUsuario.MENTOR,
            ativo=False,
            criado_em=agora_utc(),
        ),
    )
    await convidar(db, mentor)
    await db.commit()
    return mentor


async def editar(db: AsyncSession, mentor_id: UUID, dados: MentorUpdate) -> Usuario:
    mentor = await consultar(db, mentor_id, bloquear=True)
    valores = dados.model_dump(exclude_unset=True)
    mudou_email = False
    if "email" in valores:
        email = valores["email"].lower()
        existente = await get_usuario_by_email(db, email)
        if existente is not None and existente.id != mentor.id:
            email_ja_cadastrado()
        if email != mentor.email.lower():
            # Um novo endereço precisa comprovar sua posse pelo convite.
            mentor.ativo = False
            mentor.mentor_perfil_concluido_em = None
            mentor.mentor_ativado_em = None
            mentor.senha_hash = None
            mentor.email = email
            mudou_email = True
        valores["email"] = email
    for campo, valor in valores.items():
        setattr(mentor, campo, valor)
    mentor.atualizado_em = agora_utc()
    db.add(mentor)
    # Reutiliza o tratamento de colisões do índice case insensitive, inclusive em corrida.
    await criar_usuario(db, mentor)
    if mudou_email:
        await convidar(db, mentor)
    await db.commit()
    return mentor


async def reenviar_convite(db: AsyncSession, mentor_id: UUID) -> Usuario:
    mentor = await consultar(db, mentor_id, bloquear=True)
    if mentor.ativo:
        raise HTTPException(409, "Mentor já está ativo.")
    await convidar(db, mentor)
    await db.commit()
    return mentor


async def validar_convite(db: AsyncSession, token: str) -> tuple[Usuario, ConviteMentor]:
    convite = await controller.get_convite(db, hashlib.sha256(token.encode()).hexdigest())
    if convite is None:
        convite_invalido()
    # A mesma trava serializa ativação, reenvio, edição e desativação.
    mentor = await consultar(db, convite.usuario_id, bloquear=True)
    await db.refresh(convite)
    if convite.utilizado_em is not None or convite.expira_em <= agora_utc():
        convite_invalido()
    if mentor.ativo:
        convite_invalido()
    return mentor, convite


async def ativar_por_convite(db: AsyncSession, dados: MentorAtivacao) -> Usuario:
    mentor, convite = await validar_convite(db, dados.token)
    await termos_vigentes_do_hackathon(db, dados.hackathon_id)
    ids = await validar_termos_aceitos(db, dados.hackathon_id, dados.termos_ids)
    if dados.senha is not None:
        mentor.senha_hash = await asyncio.to_thread(gerar_hash, dados.senha)
    elif mentor.senha_hash is None:
        raise HTTPException(422, "Defina a senha para concluir a ativação.")
    for campo in ("nome", "empresa_parceira", "area_atuacao"):
        setattr(mentor, campo, getattr(dados, campo))
    if not mentor.max_equipes or mentor.max_equipes <= 0:
        mentor_inelegivel()
    await registrar_aceites(db, mentor.id, ids)
    agora = agora_utc()
    mentor.mentor_perfil_concluido_em = agora
    mentor.mentor_ativado_em = mentor.mentor_ativado_em or agora
    mentor.atualizado_em = agora
    mentor.ativo = True
    mentor.situacao_conta = SituacaoConta.ATIVA
    convite.utilizado_em = agora
    db.add_all([mentor, convite])
    await db.commit()
    return mentor


async def validar_elegibilidade(
    db: AsyncSession, mentor_id: UUID, hackathon_id: UUID, *, exigir_ativo: bool = True
) -> Usuario:
    """BE-S5-11: mantém a trava até o commit da atribuição e verifica perfil/termos.

    O chamador deve contar atribuições sob esta trava, conferir max_equipes e garantir
    uma única atribuição ativa por equipe na mesma transação.
    """
    mentor = await consultar(db, mentor_id, bloquear=True)
    if (
        (exigir_ativo and not mentor.ativo)
        or not mentor.mentor_perfil_concluido_em
        or not mentor.mentor_ativado_em
        or not mentor.senha_hash
        or not all((mentor.nome, mentor.empresa_parceira, mentor.area_atuacao, mentor.max_equipes))
        or mentor.max_equipes <= 0
    ):
        mentor_inelegivel()
    termos = await termos_vigentes_do_hackathon(db, hackathon_id)
    ids = await validar_termos_aceitos(db, hackathon_id, [termo.id for termo in termos])
    aceites = await listar_aceites(db, mentor.id, ids)
    if {aceite.termo_id for aceite in aceites} != set(ids):
        mentor_inelegivel()
    return mentor


async def reativar(db: AsyncSession, mentor_id: UUID, hackathon_id: UUID) -> Usuario:
    mentor = await validar_elegibilidade(db, mentor_id, hackathon_id, exigir_ativo=False)
    mentor.ativo = True
    mentor.atualizado_em = agora_utc()
    db.add(mentor)
    await db.commit()
    return mentor


async def desativar(db: AsyncSession, mentor_id: UUID) -> Usuario:
    mentor = await consultar(db, mentor_id, bloquear=True)
    mentor.ativo = False
    mentor.atualizado_em = agora_utc()
    await controller.invalidar_convites(db, mentor.id, agora_utc())
    db.add(mentor)
    await db.commit()
    return mentor
