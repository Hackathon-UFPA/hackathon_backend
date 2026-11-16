"""Composição da equipe informada pelo líder (BE-S5-01, RF18, RF24, RN01 a RN03, RN05, RN25).

Decisão de 05/11: o líder informa a categoria e toda a composição de uma vez. O que ele informa
(nome, e-mail e tipo de cada pessoa) fica separado do que cada pessoa confirma com a própria
conta: aceite dos termos e comprovante nunca passam pelo líder (RN05, RN25). A resposta mostra os
dois lados e as pendências de cada integrante.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import (
    CategoriaEquipe,
    FuncaoMembro,
    PapelUsuario,
    StatusConvite,
    TipoIntegrante,
)
from app.const.inscricao import CodigoPendencia
from app.controllers.convite import listar_convites_da_equipe, travar_convites_pendentes
from app.controllers.equipe import get_hackathon_id_da_equipe
from app.controllers.membro_equipe import get_membro, listar_membros_com_usuario, remover_membro
from app.exceptions.convite import equipe_nao_encontrada
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.equipe import (
    composicao_invalida,
    consulta_apenas_por_integrante,
    reconvite_indisponivel,
)
from app.models import Equipe, Hackathon, Usuario
from app.schemas.composicao import (
    ComposicaoResponse,
    ConfirmadoPeloIntegrante,
    IndicadoPeloLider,
    IntegranteComposicaoResponse,
)
from app.schemas.equipe import ComposicaoUpdate, IntegranteIndicado
from app.schemas.inscricao import PendenciaResponse
from app.services.convite import (
    convidar,
    equipe_e_hackathon,
    exigir_equipe_em_formacao,
    exigir_inscricoes_abertas,
    exigir_lider,
)
from app.services.homologacao import Pendencia, avaliar
from app.services.notificacao_eventos import notificar_membro_removido
from app.services.somente_leitura import exigir_equipe_editavel
from app.validations.categoria_equipe import (
    exigir_categoria_permitida,
    incoerencia_da_composicao,
    resolver_tipo,
)


@dataclass
class Indicado:
    nome: str
    email: str  # sempre em minúsculas
    tipo: TipoIntegrante


def validar_composicao(
    hackathon: Hackathon,
    categoria: CategoriaEquipe,
    *,
    tipo_lider: TipoIntegrante | None,
    email_lider: str,
    integrantes: list[IntegranteIndicado],
) -> tuple[TipoIntegrante, list[Indicado]]:
    """Confere o que o líder informou: categoria aceita pela edição, e-mails sem repetição,
    tipos coerentes com a categoria e total dentro de `min_integrantes` e `max_integrantes`
    (RN01, Q04). Devolve o tipo do líder e os indicados já normalizados. Só lê; 422 se não fecha."""
    exigir_categoria_permitida(hackathon, categoria)
    tipo_do_lider = resolver_tipo(categoria, tipo_lider, "o líder")

    indicados: list[Indicado] = []
    vistos: set[str] = set()
    repetidos: set[str] = set()
    for item in integrantes:
        email = str(item.email).lower()
        if email == email_lider.lower():
            composicao_invalida("O líder já faz parte da equipe: não o inclua em `integrantes`.")
        if email in vistos:
            repetidos.add(email)
        vistos.add(email)
        tipo = resolver_tipo(categoria, item.tipo_integrante, item.nome)
        indicados.append(Indicado(item.nome, email, tipo))
    if repetidos:
        composicao_invalida(f"E-mail repetido em `integrantes`: {', '.join(sorted(repetidos))}.")

    total = 1 + len(indicados)
    if not hackathon.min_integrantes <= total <= hackathon.max_integrantes:
        composicao_invalida(
            f"A equipe deve ter de {hackathon.min_integrantes} a {hackathon.max_integrantes} "
            f"integrantes, o líder incluído; foram informados {total}."
        )
    incoerencia = incoerencia_da_composicao(
        categoria, [tipo_do_lider, *(i.tipo for i in indicados)]
    )
    if incoerencia:
        composicao_invalida(incoerencia)
    return tipo_do_lider, indicados


def _pendencia(p: Pendencia) -> PendenciaResponse:
    return PendenciaResponse(
        codigo=p.codigo,
        mensagem=p.mensagem,
        usuario_id=p.usuario_id,
        bloqueia_conclusao=p.bloqueia_conclusao,
    )


async def montar(db: AsyncSession, equipe: Equipe, hackathon: Hackathon) -> ComposicaoResponse:
    """Estado da composição: de cada pessoa, o que o líder indicou, o que ela já confirmou e o
    que falta. Usa a mesma avaliação do painel e da homologação, então nunca diverge delas."""
    avaliacao = await avaliar(db, equipe, hackathon)
    convites = await listar_convites_da_equipe(db, equipe.id)
    aceitos = {c.usuario_id: c for c in convites if c.status == StatusConvite.ACEITO}

    integrantes: list[IntegranteComposicaoResponse] = []
    for item in avaliacao.integrantes:
        membro, usuario = item.membro, item.usuario
        convite = aceitos.get(usuario.id)
        integrantes.append(
            IntegranteComposicaoResponse(
                indicado_pelo_lider=IndicadoPeloLider(
                    nome=convite.nome if convite else usuario.nome,
                    email=convite.email if convite else usuario.email,
                    tipo_integrante=membro.tipo_integrante,
                    funcao=membro.funcao,
                ),
                confirmado_pelo_integrante=ConfirmadoPeloIntegrante(
                    integrante=True,
                    usuario_id=usuario.id,
                    convite=item.convite,
                    conta_ativa=usuario.ativo,
                    termos_aceitos=item.termos_aceitos,
                    comprovante=item.comprovante,
                ),
                pendencias=[
                    _pendencia(p) for p in avaliacao.pendencias if p.usuario_id == usuario.id
                ],
            )
        )

    abertos = 0
    for convite in avaliacao.convites_em_aberto:
        pendente = convite.status == StatusConvite.PENDENTE
        abertos += pendente
        if pendente:
            pendencia = Pendencia(
                CodigoPendencia.CONVITE_PENDENTE,
                f"{convite.nome} ainda não respondeu ao convite.",
                bloqueia_conclusao=True,
            )
        else:
            pendencia = Pendencia(
                CodigoPendencia.CONVITE_RECUSADO,
                f"{convite.nome} recusou o convite: substitua ou retire essa pessoa.",
                bloqueia_conclusao=True,
            )
        integrantes.append(
            IntegranteComposicaoResponse(
                indicado_pelo_lider=IndicadoPeloLider(
                    nome=convite.nome, email=convite.email, tipo_integrante=convite.tipo_integrante
                ),
                # usuario_id fica vazio: um convite em aberto não revela se o e-mail tem conta
                confirmado_pelo_integrante=ConfirmadoPeloIntegrante(
                    integrante=False, convite=convite.status, termos_aceitos=False
                ),
                pendencias=[_pendencia(pendencia)],
            )
        )

    return ComposicaoResponse(
        equipe_id=equipe.id,
        categoria=equipe.categoria,
        minimo_integrantes=hackathon.min_integrantes,
        maximo_integrantes=hackathon.max_integrantes,
        total_integrantes=avaliacao.total,
        total_indicados=avaliacao.total + abertos,
        integrantes=integrantes,
        pendencias_da_equipe=[_pendencia(p) for p in avaliacao.pendencias if p.usuario_id is None],
    )


async def consultar(db: AsyncSession, usuario: Usuario, equipe_id: UUID) -> ComposicaoResponse:
    """Integrantes da equipe (e DEV) veem a composição e as pendências de cada pessoa."""
    equipe, hackathon = await equipe_e_hackathon(db, equipe_id)
    if usuario.papel != PapelUsuario.DEV and await get_membro(db, equipe.id, usuario.id) is None:
        consulta_apenas_por_integrante()
    return await montar(db, equipe, hackathon)


async def editar(
    db: AsyncSession, usuario: Usuario, equipe_id: UUID, dados: ComposicaoUpdate
) -> ComposicaoResponse:
    """Substitui a composição inteira (RF24): quem não está na lista é retirado e avisado, convites
    em aberto de quem saiu são cancelados e quem é novo é convidado, tudo na mesma transação."""
    # Autoriza antes de travar qualquer coisa. Ordem dos bloqueios: convites pendentes, depois a
    # equipe, a mesma do aceite de convite (veja `travar_convites_pendentes`).
    if await get_hackathon_id_da_equipe(db, equipe_id) is None:
        equipe_nao_encontrada()
    await exigir_lider(db, equipe_id, usuario)
    await travar_convites_pendentes(db, equipe_id)
    equipe, hackathon = await equipe_e_hackathon(db, equipe_id, para_atualizar=True)
    await exigir_equipe_editavel(db, equipe.id)
    exigir_inscricoes_abertas(hackathon)
    exigir_equipe_em_formacao(equipe)

    pares = await listar_membros_com_usuario(db, equipe.id)
    lider_membro, lider_usuario = next(par for par in pares if par[0].funcao == FuncaoMembro.LIDER)
    tipo_lider, indicados = validar_composicao(
        hackathon,
        dados.categoria,
        tipo_lider=dados.tipo_lider or lider_membro.tipo_integrante,
        email_lider=lider_usuario.email,
        integrantes=dados.integrantes,
    )

    convites = await listar_convites_da_equipe(db, equipe.id)
    aceito_por_usuario = {c.usuario_id: c for c in convites if c.status == StatusConvite.ACEITO}
    pendente_por_email = {
        c.email.lower(): c for c in convites if c.status == StatusConvite.PENDENTE
    }
    # Quem já entrou é identificado pelo e-mail do convite aceito: é o que o líder digitou
    atuais = {}
    for membro, pessoa in pares:
        if membro.funcao == FuncaoMembro.LIDER:
            continue
        convite = aceito_por_usuario.get(pessoa.id)
        atuais[(convite.email if convite else pessoa.email).lower()] = (membro, pessoa, convite)

    desejados = {i.email: i for i in indicados}
    novos = [i for i in indicados if i.email not in atuais and i.email not in pendente_por_email]
    # Quem aceitou e foi retirado continua com o convite ACEITO, que ainda impede reconvidar
    ja_aceitaram = {c.email.lower() for c in convites if c.status == StatusConvite.ACEITO}
    bloqueados = sorted(i.email for i in novos if i.email in ja_aceitaram)
    if bloqueados:
        reconvite_indisponivel(bloqueados)

    try:
        removidos = [par for email, par in atuais.items() if email not in desejados]
        for membro, pessoa, _ in removidos:
            await remover_membro(db, membro)
            await notificar_membro_removido(db, equipe, pessoa.id)
        for email, convite in pendente_por_email.items():
            if email not in desejados:
                convite.status = StatusConvite.CANCELADO
                db.add(convite)
        for email, indicado in desejados.items():
            if email in atuais:
                membro, _, convite = atuais[email]
                membro.tipo_integrante = indicado.tipo
                db.add(membro)
                if convite is not None:
                    convite.tipo_integrante = indicado.tipo
                    db.add(convite)
            elif email in pendente_por_email:
                convite = pendente_por_email[email]
                convite.nome, convite.tipo_integrante = indicado.nome, indicado.tipo
                db.add(convite)
        lider_membro.tipo_integrante = tipo_lider
        db.add(lider_membro)
        equipe.categoria = dados.categoria
        equipe.atualizado_em = datetime.now(UTC)
        db.add(equipe)
        await db.flush()
        for indicado in novos:
            await convidar(db, equipe, lider_usuario, indicado.nome, indicado.email, indicado.tipo)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return await montar(db, equipe, hackathon)
