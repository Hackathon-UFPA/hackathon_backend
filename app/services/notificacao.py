"""Central de notificações in-app (BE-S5-04) e aviso do resultado (RF33).

`notificar` é a função única para qualquer fluxo avisar usuários dentro da plataforma. Ela só
usa o canal in-app: o e-mail é decidido por quem chama (`app.services.email`), e as mensagens de
chat (RN32) nunca o usam. O aviso do resultado continua em `notificacoes_resultado` (status de
envio do RF33) e ganha uma linha na central, criadas na mesma transação da homologação: se não
for possível criá-las, a homologação inteira falha.
"""

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import CanalNotificacao, StatusEnvioNotificacao, TipoNotificacao
from app.controllers.membro_equipe import listar_membros
from app.controllers.notificacao import (
    adicionar_notificacoes,
    adicionar_notificacoes_centrais,
    contar_notificacoes,
    get_notificacao_do_usuario,
    inserir_ignorando_repetidas,
    listar_notificacoes_do_usuario,
    marcar_como_lida,
    marcar_todas_como_lidas,
)
from app.controllers.resultado import listar_pareceres
from app.exceptions.notificacao import notificacao_nao_encontrada
from app.models import Notificacao, NotificacaoResultado, ResultadoProposta
from app.schemas.notificacao import (
    NotificacaoGenericaResponse,
    NotificacaoResultadoResponse,
)
from app.schemas.resultado import ParecerResponse

logger = logging.getLogger(__name__)

TITULO_RESULTADO = "Resultado do hackathon"


async def notificar(
    db: AsyncSession,
    usuario_ids: Iterable[UUID],
    tipo: TipoNotificacao,
    titulo: str,
    mensagem: str,
    *,
    chave: str,
    referencia_tipo: str | None = None,
    referencia_id: UUID | None = None,
    dados: dict | None = None,
) -> int | None:
    """Avisa os usuários na central, sem commit: roda na transação do fato gerador.

    `chave` identifica o fato (ex.: `convite:{id}`). Para um mesmo usuário, repetir a chave não
    duplica o aviso, nem com chamadas simultâneas. Devolve quantos avisos novos criou.

    Um aviso não derruba a ação principal: se a gravação falhar, o erro vai para o log, nada é
    gravado (a escrita roda num savepoint, então a transação de quem chamou segue válida) e o
    retorno é None. Para o tipo CHAT (e qualquer outro) esta função nunca enfileira e-mail.
    O tipo RESULTADO não passa por aqui: é criado junto da homologação (RF33).
    """
    if tipo == TipoNotificacao.RESULTADO:
        raise ValueError("O aviso de resultado é criado pela homologação (RF33).")
    if (referencia_tipo is None) != (referencia_id is None):
        raise ValueError("Informe o tipo e o id da referência juntos, ou nenhum dos dois.")
    destinatarios = list(dict.fromkeys(usuario_ids))
    if not destinatarios:
        return 0
    valores = [
        {
            "usuario_id": usuario_id,
            "tipo": tipo,
            "titulo": titulo,
            "mensagem": mensagem,
            "dados": jsonable_encoder(dados) if dados is not None else None,
            "referencia_tipo": referencia_tipo,
            "referencia_id": referencia_id,
            "chave_idempotencia": chave,
        }
        for usuario_id in destinatarios
    ]
    # Descarrega o que o fato gerador já escreveu, fora do try: um erro dessas escritas (ex.:
    # violação de unicidade) é de quem chamou e não pode ser engolido como falha do aviso.
    await db.flush()
    try:
        async with db.begin_nested():
            return await inserir_ignorando_repetidas(db, valores)
    except Exception:
        logger.exception(
            "Não foi possível criar a notificação %s (chave %s) para %d usuário(s)",
            tipo,
            chave,
            len(destinatarios),
        )
        return None


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
    notificacoes: list[NotificacaoResultado] = []
    centrais: list[Notificacao] = []
    for resultado in resultados:
        mensagem = _mensagem(resultado)
        for membro in await listar_membros(db, resultado.equipe_id):
            notificacao = NotificacaoResultado(
                homologacao_id=resultado.homologacao_id,
                hackathon_id=resultado.hackathon_id,
                equipe_id=resultado.equipe_id,
                submissao_id=resultado.submissao_id,
                usuario_id=membro.usuario_id,
                aprovada=resultado.aprovada,
                mensagem=mensagem,
                canal=CanalNotificacao.PLATAFORMA,
                # Na plataforma o aviso já está disponível ao integrante assim que é gravado.
                status_envio=StatusEnvioNotificacao.ENVIADO,
                enviado_em=agora,
            )
            notificacoes.append(notificacao)
            centrais.append(
                Notificacao(
                    usuario_id=membro.usuario_id,
                    tipo=TipoNotificacao.RESULTADO,
                    titulo=TITULO_RESULTADO,
                    mensagem=mensagem,
                    dados=jsonable_encoder(
                        {
                            "aprovada": resultado.aprovada,
                            "hackathon_id": resultado.hackathon_id,
                            "equipe_id": resultado.equipe_id,
                            "submissao_id": resultado.submissao_id,
                        }
                    ),
                    referencia_tipo="HOMOLOGACAO",
                    referencia_id=resultado.homologacao_id,
                    chave_idempotencia=f"resultado:{resultado.homologacao_id}:{resultado.equipe_id}",
                    notificacao_resultado_id=notificacao.id,
                )
            )
    adicionar_notificacoes(db, notificacoes)
    # Sem relationship, o ORM não ordena os INSERTs: a linha do RF33 precisa existir antes da
    # da central, que aponta para ela.
    await db.flush()
    # Sem savepoint de propósito: o resultado é atômico com a homologação.
    adicionar_notificacoes_centrais(db, centrais)
    return len(notificacoes)


async def pareceres_da_proposta(db: AsyncSession, submissao_id: UUID) -> list[ParecerResponse]:
    return [
        ParecerResponse(parecer=a.comentarios, recomendacao=a.recomendacao)
        for a in await listar_pareceres(db, submissao_id)
    ]


async def _resposta(
    db: AsyncSession,
    notificacao: Notificacao,
    resultado: NotificacaoResultado | None,
    pareceres: dict[UUID, list[ParecerResponse]],
) -> NotificacaoResultadoResponse | NotificacaoGenericaResponse:
    referencia = (
        {"tipo": notificacao.referencia_tipo, "id": notificacao.referencia_id}
        if notificacao.referencia_tipo is not None
        else None
    )
    comum = {
        "notificacao_id": notificacao.id,
        "tipo": notificacao.tipo,
        "titulo": notificacao.titulo,
        "dados": notificacao.dados,
        "referencia": referencia,
        "lida_em": notificacao.lida_em,
    }
    if resultado is None:
        return NotificacaoGenericaResponse.model_validate(
            {
                **comum,
                "id": notificacao.id,
                "mensagem": notificacao.mensagem,
                "criado_em": notificacao.criado_em,
            }
        )
    if resultado.submissao_id not in pareceres:
        pareceres[resultado.submissao_id] = await pareceres_da_proposta(db, resultado.submissao_id)
    return NotificacaoResultadoResponse.model_validate(
        {**resultado.model_dump(), **comum, "pareceres": pareceres[resultado.submissao_id]}
    )


async def listar_minhas(
    db: AsyncSession,
    usuario_id: UUID,
    *,
    lida: bool | None = None,
    tipo: TipoNotificacao | None = None,
    limite: int = 100,
    deslocamento: int = 0,
) -> tuple[list[NotificacaoResultadoResponse | NotificacaoGenericaResponse], int]:
    """Notificações do próprio usuário, da mais recente para a mais antiga, e o total que o
    filtro alcança (para o `X-Total-Count`)."""
    pareceres: dict[UUID, list[ParecerResponse]] = {}
    linhas = await listar_notificacoes_do_usuario(
        db, usuario_id, lida=lida, tipo=tipo, limite=limite, deslocamento=deslocamento
    )
    respostas = [await _resposta(db, n, r, pareceres) for n, r in linhas]
    return respostas, await contar_notificacoes(db, usuario_id, lida=lida, tipo=tipo)


async def contar_nao_lidas(db: AsyncSession, usuario_id: UUID) -> int:
    return await contar_notificacoes(db, usuario_id, lida=False)


async def marcar_lida(
    db: AsyncSession, usuario_id: UUID, notificacao_id: UUID
) -> NotificacaoResultadoResponse | NotificacaoGenericaResponse:
    """Idempotente: marcar de novo uma já lida devolve o mesmo `lida_em`. Notificação de outra
    pessoa ou inexistente dá 404, sem revelar que existe."""
    if not await marcar_como_lida(db, usuario_id, notificacao_id):
        notificacao_nao_encontrada()
    notificacao, resultado = await get_notificacao_do_usuario(db, usuario_id, notificacao_id)
    resposta = await _resposta(db, notificacao, resultado, {})
    await db.commit()
    return resposta


async def marcar_todas_lidas(db: AsyncSession, usuario_id: UUID) -> int:
    marcadas = await marcar_todas_como_lidas(db, usuario_id)
    await db.commit()
    return marcadas
