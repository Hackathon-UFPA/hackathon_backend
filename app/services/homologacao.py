"""Requisitos da inscrição e da homologação da equipe (RF22, RF23, RF25).

Há dois degraus. Para o líder concluir a inscrição, a equipe precisa ter o tamanho certo e
todos os integrantes com convite aceito, conta ativa e os termos vigentes aceitos (RN01, RN05).
Para ser homologada, além disso, todos precisam ter o comprovante de vínculo aprovado (RN25).
A mesma avaliação alimenta o painel, a conclusão e a homologação automática, então as três
nunca discordam entre si.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import (
    FuncaoMembro,
    SituacaoEquipe,
    StatusComprovante,
    StatusConvite,
    TipoTermo,
)
from app.const.inscricao import CodigoPendencia
from app.controllers.comprovante_vinculo import ultimo_comprovante_por_usuario
from app.controllers.convite import listar_convites_da_equipe, listar_usuarios_com_convite_aceito
from app.controllers.membro_equipe import listar_membros_com_usuario
from app.controllers.termo import listar_aceites_dos_usuarios, listar_termos_vigentes
from app.models import Convite, Equipe, Hackathon, MembroEquipe, Usuario
from app.validations.inscricao import como_utc, inscricoes_abertas


@dataclass
class Pendencia:
    codigo: CodigoPendencia
    mensagem: str
    usuario_id: UUID | None = None
    bloqueia_conclusao: bool = False


@dataclass
class IntegranteAvaliado:
    membro: MembroEquipe
    usuario: Usuario
    convite: StatusConvite | None
    termos_aceitos: bool
    comprovante: StatusComprovante | None


@dataclass
class Avaliacao:
    integrantes: list[IntegranteAvaliado]
    convites_em_aberto: list[Convite]
    pendencias: list[Pendencia] = field(default_factory=list)
    inscricoes_abertas: bool = False

    @property
    def total(self) -> int:
        return len(self.integrantes)

    @property
    def pode_concluir(self) -> bool:
        return not any(p.bloqueia_conclusao for p in self.pendencias)

    @property
    def homologavel(self) -> bool:
        return not self.pendencias


def _nome(usuario: Usuario) -> str:
    return usuario.nome or usuario.email


def _convites_em_aberto_ou_recusados(
    convites: list[Convite], ids_membros: set[UUID]
) -> list[Convite]:
    """O convite mais recente de cada e-mail, se ainda está em aberto ou foi recusado e a
    pessoa não entrou na equipe por outro caminho."""
    mais_recente: dict[str, Convite] = {}
    for convite in sorted(
        convites,
        key=lambda c: como_utc(c.enviado_em) if c.enviado_em else datetime.min.replace(tzinfo=UTC),
    ):
        mais_recente[convite.email.lower()] = convite
    return [
        convite
        for convite in mais_recente.values()
        if convite.status in (StatusConvite.PENDENTE, StatusConvite.RECUSADO)
        and convite.usuario_id not in ids_membros
    ]


async def avaliar(
    db: AsyncSession, equipe: Equipe, hackathon: Hackathon, *, agora: datetime | None = None
) -> Avaliacao:
    """Confere a equipe contra os requisitos e lista o que falta. Só lê o banco."""
    pares = await listar_membros_com_usuario(db, equipe.id)
    # O líder aparece primeiro; os demais seguem a ordem de entrada
    pares.sort(key=lambda par: par[0].funcao != FuncaoMembro.LIDER)
    usuarios_ids = [usuario.id for _, usuario in pares]

    vigentes = await listar_termos_vigentes(db, hackathon.id)
    vigentes_ids = {termo.id for termo in vigentes}
    termos_publicados = {termo.tipo for termo in vigentes} == set(TipoTermo)
    aceites = await listar_aceites_dos_usuarios(db, usuarios_ids, vigentes_ids)
    com_convite_aceito = await listar_usuarios_com_convite_aceito(db, equipe.id)
    comprovantes = await ultimo_comprovante_por_usuario(db, hackathon.id, usuarios_ids)
    convites = await listar_convites_da_equipe(db, equipe.id)

    integrantes: list[IntegranteAvaliado] = []
    for membro, usuario in pares:
        lider = membro.funcao == FuncaoMembro.LIDER
        comprovante = comprovantes.get(usuario.id)
        integrantes.append(
            IntegranteAvaliado(
                membro=membro,
                usuario=usuario,
                convite=None
                if lider
                else (StatusConvite.ACEITO if usuario.id in com_convite_aceito else None),
                termos_aceitos=termos_publicados and vigentes_ids <= aceites.get(usuario.id, set()),
                comprovante=comprovante.status if comprovante else None,
            )
        )

    abertas = inscricoes_abertas(hackathon, agora)
    avaliacao = Avaliacao(
        integrantes=integrantes,
        convites_em_aberto=_convites_em_aberto_ou_recusados(convites, set(usuarios_ids)),
        inscricoes_abertas=abertas,
    )
    pendencias = avaliacao.pendencias

    if equipe.situacao == SituacaoEquipe.EM_FORMACAO and not abertas:
        pendencias.append(
            Pendencia(
                CodigoPendencia.INSCRICOES_ENCERRADAS,
                "As inscrições deste hackathon não estão abertas.",
                bloqueia_conclusao=True,
            )
        )
    if avaliacao.total < hackathon.min_integrantes:
        pendencias.append(
            Pendencia(
                CodigoPendencia.EQUIPE_ABAIXO_DO_MINIMO,
                f"A equipe tem {avaliacao.total} integrante(s) e precisa de pelo menos "
                f"{hackathon.min_integrantes}.",
                bloqueia_conclusao=True,
            )
        )
    if avaliacao.total > hackathon.max_integrantes:
        pendencias.append(
            Pendencia(
                CodigoPendencia.EQUIPE_ACIMA_DO_MAXIMO,
                f"A equipe tem {avaliacao.total} integrantes e o máximo é "
                f"{hackathon.max_integrantes}.",
                bloqueia_conclusao=True,
            )
        )
    if not termos_publicados:
        pendencias.append(
            Pendencia(
                CodigoPendencia.TERMOS_NAO_PUBLICADOS,
                "O regulamento e o termo de consentimento vigentes ainda não foram publicados.",
                bloqueia_conclusao=True,
            )
        )

    for integrante in integrantes:
        usuario = integrante.usuario
        nome = _nome(usuario)
        if not usuario.ativo:
            pendencias.append(
                Pendencia(
                    CodigoPendencia.CONTA_DESATIVADA,
                    f"A conta de {nome} está desativada.",
                    usuario.id,
                    bloqueia_conclusao=True,
                )
            )
        if integrante.membro.funcao != FuncaoMembro.LIDER and integrante.convite is None:
            pendencias.append(
                Pendencia(
                    CodigoPendencia.CONVITE_NAO_ACEITO,
                    f"{nome} não tem convite aceito nesta equipe.",
                    usuario.id,
                    bloqueia_conclusao=True,
                )
            )
        if termos_publicados and not integrante.termos_aceitos:
            pendencias.append(
                Pendencia(
                    CodigoPendencia.TERMOS_NAO_ACEITOS,
                    f"{nome} precisa aceitar o regulamento e o termo de consentimento vigentes.",
                    usuario.id,
                    bloqueia_conclusao=True,
                )
            )
        # O comprovante só pesa na homologação: não impede a conclusão da inscrição
        if integrante.comprovante is None:
            pendencias.append(
                Pendencia(
                    CodigoPendencia.COMPROVANTE_NAO_ENVIADO,
                    f"{nome} ainda não enviou o comprovante de vínculo.",
                    usuario.id,
                )
            )
        elif integrante.comprovante == StatusComprovante.PENDENTE:
            pendencias.append(
                Pendencia(
                    CodigoPendencia.COMPROVANTE_PENDENTE,
                    f"O comprovante de {nome} aguarda conferência.",
                    usuario.id,
                )
            )
        elif integrante.comprovante == StatusComprovante.RECUSADO:
            pendencias.append(
                Pendencia(
                    CodigoPendencia.COMPROVANTE_RECUSADO,
                    f"O comprovante de {nome} foi recusado e precisa ser enviado de novo.",
                    usuario.id,
                )
            )
    return avaliacao


async def reavaliar_homologacao(
    db: AsyncSession, equipe: Equipe, hackathon: Hackathon
) -> SituacaoEquipe:
    """Aplica a homologação automática, nos dois sentidos (RF23). Sem commit.

    AGUARDANDO_HOMOLOGACAO vira HOMOLOGADA quando todos os requisitos valem, e HOMOLOGADA volta
    para AGUARDANDO_HOMOLOGACAO quando algum deixa de valer. Equipes em formação ou já
    marcadas como NAO_HOMOLOGADA não mudam. Quem chama precisa ter travado a linha da equipe.
    """
    if equipe.situacao not in (SituacaoEquipe.AGUARDANDO_HOMOLOGACAO, SituacaoEquipe.HOMOLOGADA):
        return equipe.situacao

    homologavel = (await avaliar(db, equipe, hackathon)).homologavel
    agora = datetime.now(UTC)
    if homologavel and equipe.situacao == SituacaoEquipe.AGUARDANDO_HOMOLOGACAO:
        equipe.situacao = SituacaoEquipe.HOMOLOGADA
        equipe.homologada_em = agora
    elif not homologavel and equipe.situacao == SituacaoEquipe.HOMOLOGADA:
        equipe.situacao = SituacaoEquipe.AGUARDANDO_HOMOLOGACAO
        equipe.homologada_em = None
    else:
        return equipe.situacao

    equipe.atualizado_em = agora
    db.add(equipe)
    await db.flush()
    return equipe.situacao
