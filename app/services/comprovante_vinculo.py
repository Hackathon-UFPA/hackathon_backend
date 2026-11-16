"""Conferência do comprovante de vínculo e reenvio depois de recusa (RF21, RN25)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import SituacaoConta, StatusComprovante, TipoIntegrante
from app.controllers.autodeclaracao import (
    get_autodeclaracoes_por_id,
    listar_autodeclaracoes,
)
from app.controllers.comprovante_vinculo import (
    criar_comprovante,
    get_comprovante_by_id,
    get_ultimo_comprovante,
    listar_comprovantes,
    listar_comprovantes_do_usuario,
)
from app.controllers.hackathon import get_hackathon_com_inscricoes
from app.controllers.membro_equipe import get_membro_no_hackathon
from app.exceptions.auth import inscricoes_indisponiveis
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.inscricao import (
    comprovante_ativo_existente,
    comprovante_ja_decidido,
    comprovante_nao_encontrado,
)
from app.models import AutodeclaracaoVinculo, ComprovanteVinculo, Usuario
from app.schemas.autodeclaracao import AutodeclaracaoResponse
from app.schemas.comprovante_vinculo import (
    ComprovanteAdminResponse,
    ComprovanteEnvio,
    ComprovanteVinculoResponse,
    UsuarioResumo,
)
from app.services.inscricao import reavaliar_equipe_do_usuario


def _resposta(
    comprovante: ComprovanteVinculo,
    usuario: Usuario,
    declaracao: AutodeclaracaoVinculo | None = None,
) -> ComprovanteAdminResponse:
    base = ComprovanteVinculoResponse.model_validate(comprovante).model_dump()
    return ComprovanteAdminResponse(
        **base,
        usuario=UsuarioResumo.model_validate(usuario),
        autodeclaracao=AutodeclaracaoResponse.model_validate(declaracao) if declaracao else None,
    )


async def listar(
    db: AsyncSession,
    *,
    status: StatusComprovante,
    hackathon_id: UUID | None,
    limite: int,
    deslocamento: int,
) -> list[ComprovanteAdminResponse]:
    """Fila de conferência, com o link do arquivo para o conferente abrir."""
    pares = await listar_comprovantes(
        db,
        status=status,
        hackathon_id=hackathon_id,
        limite=limite,
        deslocamento=deslocamento,
    )
    declaracoes = await get_autodeclaracoes_por_id(
        db, [c.autodeclaracao_id for c, _ in pares if c.autodeclaracao_id]
    )
    return [
        _resposta(comprovante, usuario, declaracoes.get(comprovante.autodeclaracao_id))
        for comprovante, usuario in pares
    ]


async def _comprovante_pendente(db: AsyncSession, comprovante_id: UUID) -> ComprovanteVinculo:
    comprovante = await get_comprovante_by_id(db, comprovante_id, para_atualizar=True)
    if comprovante is None:
        comprovante_nao_encontrado()
    if comprovante.status != StatusComprovante.PENDENTE:
        comprovante_ja_decidido()
    return comprovante


async def aprovar(
    db: AsyncSession, validador: Usuario, comprovante_id: UUID
) -> ComprovanteAdminResponse:
    """Aprova o vínculo: a conta da pessoa passa a ATIVA (RN25) e a equipe dela é reavaliada
    para a homologação automática (RF23), tudo na mesma transação."""
    comprovante = await _comprovante_pendente(db, comprovante_id)
    agora = datetime.now(UTC)
    comprovante.status = StatusComprovante.APROVADO
    comprovante.validado_por = validador.id
    comprovante.validado_em = agora
    db.add(comprovante)

    usuario = await db.get(Usuario, comprovante.usuario_id)
    if usuario.situacao_conta == SituacaoConta.PENDENTE:
        usuario.situacao_conta = SituacaoConta.ATIVA
        usuario.atualizado_em = agora
        db.add(usuario)
    await db.flush()

    try:
        await reavaliar_equipe_do_usuario(db, comprovante.hackathon_id, usuario.id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(comprovante)
    ids = [comprovante.autodeclaracao_id] if comprovante.autodeclaracao_id else []
    declaracoes = await get_autodeclaracoes_por_id(db, ids)
    return _resposta(comprovante, usuario, declaracoes.get(comprovante.autodeclaracao_id))


async def recusar(
    db: AsyncSession, validador: Usuario, comprovante_id: UUID, motivo: str
) -> ComprovanteAdminResponse:
    """Recusa com motivo. A pessoa vê o motivo em `GET /comprovantes/meus` e pode enviar outro
    comprovante (RF21, Q25)."""
    comprovante = await _comprovante_pendente(db, comprovante_id)
    comprovante.status = StatusComprovante.RECUSADO
    comprovante.motivo_recusa = motivo
    comprovante.validado_por = validador.id
    comprovante.validado_em = datetime.now(UTC)
    db.add(comprovante)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    await db.refresh(comprovante)
    usuario = await db.get(Usuario, comprovante.usuario_id)
    ids = [comprovante.autodeclaracao_id] if comprovante.autodeclaracao_id else []
    declaracoes = await get_autodeclaracoes_por_id(db, ids)
    return _resposta(comprovante, usuario, declaracoes.get(comprovante.autodeclaracao_id))


async def listar_meus(db: AsyncSession, usuario: Usuario) -> list[ComprovanteVinculo]:
    return await listar_comprovantes_do_usuario(db, usuario.id)


async def _tipo_e_declaracao(
    db: AsyncSession, usuario: Usuario, hackathon_id
) -> tuple[TipoIntegrante, AutodeclaracaoVinculo | None]:
    """O vínculo que o novo comprovante comprova: o que o líder indicou, se a pessoa já está em
    uma equipe da edição; senão o que ela declarou; senão o acadêmico, como antes da BE-S5-03.
    A declaração ligada é a mais recente do mesmo tipo."""
    declaracoes = await listar_autodeclaracoes(db, usuario.id, hackathon_id)
    membro = await get_membro_no_hackathon(db, hackathon_id, usuario.id)
    if membro is not None:
        tipo = membro.tipo_integrante
    elif declaracoes:
        tipo = declaracoes[0].tipo
    else:
        tipo = TipoIntegrante.ESTUDANTE
    return tipo, next((d for d in declaracoes if d.tipo == tipo), None)


async def reenviar(
    db: AsyncSession, usuario: Usuario, dados: ComprovanteEnvio
) -> ComprovanteVinculo:
    """Novo comprovante depois de uma recusa; o anterior fica no histórico. Vale para o
    hackathon com inscrições abertas, como no cadastro."""
    hackathon = await get_hackathon_com_inscricoes(db)
    if hackathon is None:
        inscricoes_indisponiveis()

    # Quem é o dono do documento e qual vínculo ele comprova vêm do servidor, nunca do pedido
    tipo, declaracao = await _tipo_e_declaracao(db, usuario, hackathon.id)
    ultimo = await get_ultimo_comprovante(db, usuario.id, hackathon.id, tipo)
    if ultimo is not None and ultimo.status != StatusComprovante.RECUSADO:
        comprovante_ativo_existente()

    try:
        comprovante = await criar_comprovante(
            db,
            ComprovanteVinculo(
                usuario_id=usuario.id,
                hackathon_id=hackathon.id,
                arquivo_url=str(dados.arquivo_url),
                tipo_vinculo=tipo,
                autodeclaracao_id=declaracao.id if declaracao else None,
            ),
        )
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        # Dois envios ao mesmo tempo: o índice único parcial decide
        if "uq_comprovantes_vinculo_ativo" in str(error.orig):
            comprovante_ativo_existente()
        erro_de_integridade_sql(error)
    await db.refresh(comprovante)
    return comprovante
