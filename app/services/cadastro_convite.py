"""Cadastro próprio de quem foi convidado para uma equipe sem ter conta (BE-S5-02; RF01, RF18,
RF19, RN01 a RN06).

O líder nunca cria conta nem define senha: ele só indica nome e e-mail. A pessoa recebe um link de
uso único e cria o próprio acesso com a própria senha. O token prova a posse do e-mail do convite,
então o endereço já nasce confirmado. A conta nasce `PENDENTE` (RN25): o vínculo continua sendo
comprovado e conferido à parte. Cadastrar não aceita o convite nem os termos; isso a pessoa faz
depois, com a própria conta, em `POST /convites/{id}/aceitar`.
"""

import asyncio
from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, SituacaoConta, SituacaoEquipe, StatusConvite
from app.controllers.comprovante_vinculo import criar_comprovante
from app.controllers.convite import get_convite_por_token_hash
from app.controllers.equipe import get_equipe_by_id, get_hackathon_by_id
from app.controllers.usuario import criar_usuario, get_usuario_by_email
from app.exceptions.convite import conta_ja_existe_para_o_convite, link_de_convite_invalido
from app.models import ComprovanteVinculo, Convite, Equipe, Hackathon, Usuario
from app.schemas.cadastro_convite import (
    CadastroPorConviteRequest,
    ConviteCadastroConsultaResponse,
)
from app.security.senha import gerar_hash
from app.services.convite import associar_convites_pendentes
from app.services.token_usuario import hash_do_token
from app.validations.inscricao import como_utc, inscricoes_abertas


async def _convite_do_token(
    db: AsyncSession, token: str, *, bloquear: bool = False
) -> tuple[Convite, Equipe, Hackathon]:
    """Acha o convite do link. Token desconhecido, vencido, já usado, convite que não está mais
    pendente, equipe que já fechou a composição ou inscrições encerradas dão sempre a mesma
    resposta: o link não revela o que existe. Com `bloquear`, trava o convite: dois usos
    simultâneos do mesmo link viram um sucesso e uma recusa."""
    convite = await get_convite_por_token_hash(db, hash_do_token(token), para_atualizar=bloquear)
    if convite is None:
        link_de_convite_invalido()
    if bloquear:
        # Depois de esperar a trava, a linha pode ter sido gasta pelo outro pedido
        await db.refresh(convite)
    if (
        convite.status != StatusConvite.PENDENTE
        or convite.token_utilizado_em is not None
        or convite.token_expira_em is None
        or como_utc(convite.token_expira_em) <= datetime.now(UTC)
    ):
        link_de_convite_invalido()
    equipe = await get_equipe_by_id(db, convite.equipe_id)
    hackathon = await get_hackathon_by_id(db, equipe.hackathon_id)
    if equipe.situacao != SituacaoEquipe.EM_FORMACAO or not inscricoes_abertas(hackathon):
        link_de_convite_invalido()
    return convite, equipe, hackathon


async def consultar(db: AsyncSession, token: str) -> ConviteCadastroConsultaResponse:
    """Dados do convite para a página de cadastro. Não consome o token."""
    convite, equipe, _ = await _convite_do_token(db, token)
    lider = await db.get(Usuario, convite.convidado_por)
    return ConviteCadastroConsultaResponse(
        email=convite.email,
        nome=convite.nome,
        equipe_nome=equipe.nome,
        lider_nome=lider.nome if lider else None,
        tipo_integrante=convite.tipo_integrante,
        expira_em=convite.token_expira_em,
    )


async def cadastrar(db: AsyncSession, dados: CadastroPorConviteRequest) -> Usuario:
    """Cria a conta do convidado, com e-mail confirmado e conta pendente, e liga a ela os convites
    em aberto do mesmo endereço, tudo em uma transação: se algo falhar, o link continua valendo."""
    try:
        convite, _, hackathon = await _convite_do_token(db, dados.token, bloquear=True)
        if await get_usuario_by_email(db, convite.email) is not None:
            conta_ja_existe_para_o_convite()

        agora = datetime.now(UTC)
        usuario = await criar_usuario(
            db,
            Usuario(
                nome=dados.nome or convite.nome,
                email=convite.email.lower(),
                papel=PapelUsuario.PARTICIPANTE,
                instituicao=dados.instituicao,
                curso=dados.curso,
                periodo=dados.periodo,
                senha_hash=await asyncio.to_thread(gerar_hash, dados.senha),
                situacao_conta=SituacaoConta.PENDENTE,
                email_confirmado_em=agora,
            ),
        )
        if dados.comprovante_url is not None:
            await criar_comprovante(
                db,
                ComprovanteVinculo(
                    usuario_id=usuario.id,
                    hackathon_id=hackathon.id,
                    arquivo_url=str(dados.comprovante_url),
                    # O vínculo que o líder indicou no convite é o que a homologação confere
                    # (BE-S5-03): sem isto um convidado PROFISSIONAL entraria com comprovante
                    # acadêmico e teria de reenviar
                    tipo_vinculo=convite.tipo_integrante,
                ),
            )
        convite.token_utilizado_em = agora
        db.add(convite)
        await associar_convites_pendentes(db, usuario)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(usuario)
    return usuario
