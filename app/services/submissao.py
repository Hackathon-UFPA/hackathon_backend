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
from app.controllers.equipe import get_equipe_by_id, get_hackathon_id_da_equipe
from app.controllers.hackathon import get_hackathon_compartilhado
from app.controllers.membro_equipe import get_membro
from app.controllers.protocolo import criar_protocolo, get_protocolo_da_proposta
from app.controllers.submissao import (
    atualizar_submissao,
    criar_submissao,
    get_submissao_da_equipe,
    salvar_envio,
)
from app.controllers.tema import get_tema_by_id
from app.controllers.versao_proposta import (
    criar_versao,
    get_numero_da_versao,
    listar_versoes,
    proposta_foi_distribuida,
    proposta_tem_avaliacao,
    proximo_numero,
)
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
    proposta_nao_enviada_para_reenvio,
    rascunho_nao_encontrado,
    reenvio_bloqueado,
    tema_nao_disponivel,
    tema_nao_encontrado,
)
from app.models import Equipe, Hackathon, Protocolo, Submissao, Usuario, VersaoProposta
from app.schemas.protocolo import ProtocoloResponse
from app.schemas.submissao import (
    SubmissaoCreate,
    SubmissaoEnviadaResponse,
    SubmissaoReenvio,
    SubmissaoResponse,
    SubmissaoUpdate,
    VersaoPropostaResponse,
)
from app.services.email_eventos import avisar_protocolo_proposta
from app.services.equipe import consultar
from app.services.resultado import exigir_resultado_aberto
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


def _resposta_enviada(
    proposta: Submissao, protocolo: Protocolo, versao: int | None
) -> SubmissaoEnviadaResponse:
    return SubmissaoEnviadaResponse(
        **SubmissaoResponse.model_validate(proposta).model_dump(),
        protocolo=ProtocoloResponse.model_validate(protocolo),
        versao=versao,
    )


async def _travar_edicao(db: AsyncSession, equipe_id: UUID) -> Hackathon:
    """Primeiro lock do envio e do reenvio: a edição em modo compartilhado (FOR SHARE).

    A distribuição, a avaliação e a homologação do resultado travam a mesma linha com
    FOR UPDATE, então nenhum envio passa no meio delas, e um envio em andamento termina antes
    de a homologação ler as propostas. Ordem dos locks: edição -> equipe -> proposta."""
    hackathon_id = await get_hackathon_id_da_equipe(db, equipe_id)
    if hackathon_id is None:
        equipe_nao_encontrada()
    hackathon = await get_hackathon_compartilhado(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    return hackathon


async def _registrar_envio(
    db: AsyncSession, usuario: Usuario, equipe: Equipe, proposta: Submissao
) -> tuple[Protocolo, int]:
    """Emite o protocolo e grava a versão imutável com o conteúdo enviado (BE-S5-09)."""
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
    numero = await proximo_numero(db, proposta.id)
    await criar_versao(
        db,
        VersaoProposta(
            submissao_id=proposta.id,
            numero=numero,
            tema_id=proposta.tema_id,
            titulo=proposta.titulo,
            descricao=proposta.descricao,
            ods=list(proposta.ods) if proposta.ods is not None else None,
            bases_dados=proposta.bases_dados,
            documento_url=proposta.documento_url,
            protocolo_id=protocolo.id,
            enviada_por=usuario.id,
            enviada_em=proposta.enviado_em,
        ),
    )
    await avisar_protocolo_proposta(db, equipe, proposta, protocolo)
    return protocolo, numero


def _tratar_integridade_do_envio(error: IntegrityError):
    if "uq_versoes_proposta_numero" in str(error.orig):
        proposta_ja_enviada()
    erro_de_integridade_sql(error)


async def enviar(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> SubmissaoEnviadaResponse:
    try:
        hackathon = await _travar_edicao(db, equipe_id)
        equipe = await _equipe_para_escrita(db, usuario, equipe_id)
        # Com o resultado homologado, nenhuma proposta nova entra (RF31).
        await exigir_resultado_aberto(db, hackathon.id)
        if equipe.situacao != SituacaoEquipe.HOMOLOGADA:
            equipe_nao_homologada()
        # Ordem compartilhada com a edição do rascunho: equipe -> proposta.
        proposta = await get_submissao_da_equipe(db, equipe.id, para_atualizar=True)
        if proposta is None:
            rascunho_nao_encontrado()
        if proposta.status == StatusProposta.ENVIADA:
            proposta_ja_enviada()
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
        protocolo, numero = await _registrar_envio(db, usuario, equipe, proposta)
        resposta = _resposta_enviada(proposta, protocolo, numero)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade_do_envio(error)
    except Exception:
        await db.rollback()
        raise
    return resposta


async def reenviar(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, dados: SubmissaoReenvio
) -> SubmissaoEnviadaResponse:
    """RF27/RN08 (BE-S5-09): nova versão da proposta já enviada, com conteúdo completo, até o
    fim do prazo de propostas e só enquanto ela não foi distribuída, avaliada nem homologada.
    A versão anterior e o protocolo dela ficam no histórico; a nova ganha protocolo próprio."""
    try:
        hackathon = await _travar_edicao(db, equipe_id)
        equipe = await _equipe_para_escrita(db, usuario, equipe_id)
        await exigir_resultado_aberto(db, hackathon.id)
        if equipe.situacao != SituacaoEquipe.HOMOLOGADA:
            equipe_nao_homologada()
        proposta = await get_submissao_da_equipe(db, equipe.id, para_atualizar=True)
        if proposta is None or proposta.status != StatusProposta.ENVIADA:
            proposta_nao_enviada_para_reenvio()
        agora = datetime.now(UTC)
        if not propostas_abertas(hackathon, agora):
            fora_do_periodo_de_propostas()
        if await proposta_foi_distribuida(db, proposta.id):
            reenvio_bloqueado("a proposta já foi distribuída aos avaliadores.")
        if await proposta_tem_avaliacao(db, proposta.id):
            reenvio_bloqueado("a proposta já tem avaliação registrada.")
        await _validar_tema(db, equipe, dados.tema_id)

        for campo, valor in dados.model_dump().items():
            setattr(proposta, campo, valor)
        pendentes = campos_obrigatorios_pendentes(proposta)
        if pendentes:
            proposta_incompleta(pendentes)
        proposta.enviado_em = agora
        proposta.atualizado_em = agora
        await salvar_envio(db, proposta)
        protocolo, numero = await _registrar_envio(db, usuario, equipe, proposta)
        resposta = _resposta_enviada(proposta, protocolo, numero)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        _tratar_integridade_do_envio(error)
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
    return _resposta_enviada(proposta, protocolo, await get_numero_da_versao(db, protocolo.id))


async def consultar_versoes(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID
) -> list[VersaoPropostaResponse]:
    """Histórico dos envios, da versão mais recente para a original. Só integrantes e DEV."""
    await consultar(db, usuario, equipe_id)
    proposta = await get_submissao_da_equipe(db, equipe_id)
    if proposta is None or proposta.status != StatusProposta.ENVIADA:
        proposta_enviada_nao_encontrada()
    return [
        VersaoPropostaResponse(
            numero=versao.numero,
            tema_id=versao.tema_id,
            titulo=versao.titulo,
            descricao=versao.descricao,
            ods=versao.ods,
            bases_dados=versao.bases_dados,
            documento_url=versao.documento_url,
            enviada_por=versao.enviada_por,
            enviada_em=versao.enviada_em,
            protocolo=ProtocoloResponse.model_validate(protocolo),
        )
        for versao, protocolo in await listar_versoes(db, proposta.id)
    ]
