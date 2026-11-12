from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import (
    FuncaoMembro,
    PapelUsuario,
    SituacaoEquipe,
    StatusProposta,
    TipoProtocolo,
)
from app.controllers.equipe import get_equipe_by_id, get_hackathon_by_id
from app.controllers.membro_equipe import get_membro
from app.controllers.protocolo import criar_protocolo, get_protocolo_da_proposta
from app.controllers.submissao import (
    atualizar_submissao,
    criar_submissao,
    get_submissao_da_equipe,
    salvar_envio,
)
from app.controllers.tema import get_tema_by_id
from app.exceptions.convite import (
    apenas_lider_da_equipe,
    equipe_nao_encontrada,
    hackathon_nao_encontrado,
)
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.submissao import (
    equipe_nao_homologada,
    equipe_somente_leitura,
    fora_do_periodo_de_propostas,
    proposta_enviada_nao_encontrada,
    proposta_incompleta,
    proposta_ja_enviada,
    proposta_ja_existente,
    proposta_nao_editavel,
    rascunho_nao_encontrado,
    tema_nao_disponivel,
    tema_nao_encontrado,
)
from app.models import Equipe, Protocolo, Submissao, Usuario
from app.schemas.protocolo import ProtocoloResponse
from app.schemas.submissao import (
    SubmissaoCreate,
    SubmissaoEnviadaResponse,
    SubmissaoResponse,
    SubmissaoUpdate,
)
from app.services.email_eventos import avisar_protocolo_proposta
from app.services.equipe import consultar
from app.services.somente_leitura import exigir_equipe_editavel
from app.validations.submissao import campos_obrigatorios_pendentes, propostas_abertas


async def _equipe_para_escrita(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> Equipe:
    # A mesma ordem de locks deve ser usada no envio: equipe antes da proposta.
    equipe = await get_equipe_by_id(db, equipe_id, para_atualizar=True)
    if equipe is None:
        equipe_nao_encontrada()
    if usuario.papel != PapelUsuario.DEV:
        membro = await get_membro(db, equipe.id, usuario.id)
        if membro is None or membro.funcao != FuncaoMembro.LIDER:
            apenas_lider_da_equipe()
    await exigir_equipe_editavel(db, equipe.id)
    if equipe.situacao == SituacaoEquipe.NAO_HOMOLOGADA:
        equipe_somente_leitura()
    return equipe


async def _validar_tema(db: AsyncSession, equipe: Equipe, tema_id: UUID | None) -> None:
    if tema_id is None:
        return
    tema = await get_tema_by_id(db, tema_id)
    if tema is None:
        tema_nao_encontrado()
    if not tema.ativo or tema.hackathon_id != equipe.hackathon_id:
        tema_nao_disponivel()


async def criar(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, dados: SubmissaoCreate
) -> Submissao:
    equipe = await _equipe_para_escrita(db, usuario, equipe_id)
    if await get_submissao_da_equipe(db, equipe.id) is not None:
        proposta_ja_existente()
    await _validar_tema(db, equipe, dados.tema_id)
    agora = datetime.now(UTC)
    proposta = Submissao(
        **dados.model_dump(),
        equipe_id=equipe.id,
        hackathon_id=equipe.hackathon_id,
        status=StatusProposta.RASCUNHO,
        criado_em=agora,
        atualizado_em=agora,
    )
    try:
        await criar_submissao(db, proposta)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if "uq_submissoes_equipe" in str(error.orig):
            proposta_ja_existente()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(proposta)
    return proposta


async def consultar_rascunho(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> Submissao:
    await consultar(db, usuario, equipe_id)
    proposta = await get_submissao_da_equipe(db, equipe_id)
    if proposta is None or proposta.status != StatusProposta.RASCUNHO:
        rascunho_nao_encontrado()
    return proposta


async def editar(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, dados: SubmissaoUpdate
) -> Submissao:
    equipe = await _equipe_para_escrita(db, usuario, equipe_id)
    proposta = await get_submissao_da_equipe(db, equipe.id, para_atualizar=True)
    if proposta is None:
        rascunho_nao_encontrado()
    if proposta.status != StatusProposta.RASCUNHO:
        proposta_nao_editavel()
    # Um tema antigo inativo não impede o salvamento de outros campos.
    if "tema_id" in dados.model_fields_set:
        await _validar_tema(db, equipe, dados.tema_id)
    try:
        proposta.atualizado_em = datetime.now(UTC)
        await atualizar_submissao(db, proposta, dados)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(proposta)
    return proposta


def _resposta_enviada(proposta: Submissao, protocolo: Protocolo) -> SubmissaoEnviadaResponse:
    return SubmissaoEnviadaResponse(
        **SubmissaoResponse.model_validate(proposta).model_dump(),
        protocolo=ProtocoloResponse.model_validate(protocolo),
    )


async def enviar(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> SubmissaoEnviadaResponse:
    try:
        equipe = await _equipe_para_escrita(db, usuario, equipe_id)
        if equipe.situacao != SituacaoEquipe.HOMOLOGADA:
            equipe_nao_homologada()
        # Ordem compartilhada com a edição do rascunho: equipe -> proposta.
        proposta = await get_submissao_da_equipe(db, equipe.id, para_atualizar=True)
        if proposta is None:
            rascunho_nao_encontrado()
        if proposta.status == StatusProposta.ENVIADA:
            proposta_ja_enviada()
        hackathon = await get_hackathon_by_id(db, equipe.hackathon_id)
        if hackathon is None:
            hackathon_nao_encontrado()
        agora = datetime.now(UTC)
        if not propostas_abertas(hackathon, agora):
            fora_do_periodo_de_propostas()
        pendentes = campos_obrigatorios_pendentes(proposta)
        if pendentes:
            proposta_incompleta(pendentes)
        await _validar_tema(db, equipe, proposta.tema_id)

        proposta.status = StatusProposta.ENVIADA
        proposta.enviado_em = agora
        await salvar_envio(db, proposta)
        protocolo = await criar_protocolo(
            db,
            Protocolo(
                tipo=TipoProtocolo.PROPOSTA,
                equipe_id=equipe.id,
                submissao_id=proposta.id,
                emitido_por=usuario.id,
                emitido_em=proposta.enviado_em,
            ),
        )
        await avisar_protocolo_proposta(db, equipe, proposta, protocolo)
        resposta = _resposta_enviada(proposta, protocolo)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if "uq_protocolos_proposta_submissao" in str(error.orig):
            proposta_ja_enviada()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return resposta


async def consultar_enviada(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID
) -> SubmissaoEnviadaResponse:
    await consultar(db, usuario, equipe_id)
    proposta = await get_submissao_da_equipe(db, equipe_id)
    if proposta is None or proposta.status != StatusProposta.ENVIADA:
        proposta_enviada_nao_encontrada()
    protocolo = await get_protocolo_da_proposta(db, equipe_id)
    if protocolo is None:
        proposta_enviada_nao_encontrada()
    return _resposta_enviada(proposta, protocolo)
