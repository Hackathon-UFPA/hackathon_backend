"""Notificação do resultado aos integrantes da equipe (RF33).

Canal atual: plataforma. O e-mail depende da decisão Q16 e fica como ponto de extensão em
`app.integrations.email`. As linhas são criadas na mesma transação da homologação: se não
for possível criá-las, a homologação inteira falha.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import CanalNotificacao, StatusEnvioNotificacao
from app.controllers.membro_equipe import listar_membros
from app.controllers.notificacao import adicionar_notificacoes, listar_notificacoes_do_usuario
from app.controllers.resultado import listar_pareceres
from app.models import NotificacaoResultado, ResultadoProposta
from app.schemas.notificacao import NotificacaoResultadoResponse
from app.schemas.resultado import ParecerResponse


def _mensagem(resultado: ResultadoProposta) -> str:
    titulo = f" '{resultado.titulo}'" if resultado.titulo else ""
    if resultado.aprovada:
        situacao = "foi APROVADA"
    else:
        situacao = (
            "NÃO foi aprovada. A equipe passa ao modo somente leitura: pode consultar o "
            "painel, a proposta e o parecer"
        )
    return (
        f"O resultado do hackathon foi homologado: a proposta{titulo} da equipe {situacao}. "
        f"Consulte o parecer em GET /equipes/{resultado.equipe_id}/resultado."
    )


async def criar_notificacoes_do_resultado(
    db: AsyncSession, resultados: list[ResultadoProposta]
) -> int:
    """Uma notificação por integrante de cada equipe com proposta no resultado, aprovada ou
    não. Chamada dentro da transação da homologação. Devolve quantas criou."""
    agora = datetime.now(UTC)
    notificacoes = [
        NotificacaoResultado(
            homologacao_id=resultado.homologacao_id,
            hackathon_id=resultado.hackathon_id,
            equipe_id=resultado.equipe_id,
            submissao_id=resultado.submissao_id,
            usuario_id=membro.usuario_id,
            aprovada=resultado.aprovada,
            mensagem=_mensagem(resultado),
            canal=CanalNotificacao.PLATAFORMA,
            # Na plataforma o aviso já está disponível ao integrante assim que é gravado.
            status_envio=StatusEnvioNotificacao.ENVIADO,
            enviado_em=agora,
        )
        for resultado in resultados
        for membro in await listar_membros(db, resultado.equipe_id)
    ]
    adicionar_notificacoes(db, notificacoes)
    return len(notificacoes)


async def pareceres_da_proposta(db: AsyncSession, submissao_id: UUID) -> list[ParecerResponse]:
    return [
        ParecerResponse(parecer=a.comentarios, recomendacao=a.recomendacao)
        for a in await listar_pareceres(db, submissao_id)
    ]


async def listar_minhas(db: AsyncSession, usuario_id: UUID) -> list[NotificacaoResultadoResponse]:
    pareceres: dict[UUID, list[ParecerResponse]] = {}
    respostas = []
    for notificacao in await listar_notificacoes_do_usuario(db, usuario_id):
        if notificacao.submissao_id not in pareceres:
            pareceres[notificacao.submissao_id] = await pareceres_da_proposta(
                db, notificacao.submissao_id
            )
        respostas.append(
            NotificacaoResultadoResponse.model_validate(
                {
                    **notificacao.model_dump(),
                    "pareceres": pareceres[notificacao.submissao_id],
                }
            )
        )
    return respostas
