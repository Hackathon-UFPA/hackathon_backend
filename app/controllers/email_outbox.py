from uuid import UUID

from sqlalchemy import func, or_, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusEmail, TipoEmail
from app.controllers.usuario import mesma_organizacao_sql
from app.db.defaults import AGORA_UTC
from app.models import EmailOutbox, Usuario


async def adicionar_email(db: AsyncSession, valores: dict) -> UUID | None:
    """Grava na fila sem commit. Devolve o id, ou None se a chave de idempotência já existe."""
    comando = (
        insert(EmailOutbox)
        .values(**valores)
        .on_conflict_do_nothing(index_elements=["chave_idempotencia"])
        .returning(col(EmailOutbox.id))
    )
    return (await db.exec(comando)).scalar_one_or_none()


async def get_email(
    db: AsyncSession, email_id: UUID, *, para_atualizar: bool = False
) -> EmailOutbox | None:
    consulta = select(EmailOutbox).where(EmailOutbox.id == email_id)
    if para_atualizar:
        consulta = consulta.with_for_update()
    return (await db.exec(consulta)).first()


async def listar_emails(
    db: AsyncSession,
    *,
    status: StatusEmail | None,
    tipo: TipoEmail | None,
    destinatario: str | None,
    limite: int,
    deslocamento: int,
    organizacao_id: UUID | None = None,
    todas_as_organizacoes: bool = True,
) -> list[EmailOutbox]:
    """Mais recentes primeiro; o id desempata para a ordem ser determinística. Fora de
    `todas_as_organizacoes`, só os e-mails para contas da organização informada."""
    consulta = (
        select(EmailOutbox)
        .order_by(col(EmailOutbox.criado_em).desc(), col(EmailOutbox.id))
        .limit(limite)
        .offset(deslocamento)
    )
    if not todas_as_organizacoes:
        da_organizacao = col(EmailOutbox.usuario_id).in_(
            select(Usuario.id).where(mesma_organizacao_sql(Usuario.organizacao_id, organizacao_id))
        )
        # E-mail sem conta ligada conta como "sem organização", como os demais dados antigos
        if organizacao_id is None:
            da_organizacao = or_(da_organizacao, col(EmailOutbox.usuario_id).is_(None))
        consulta = consulta.where(da_organizacao)
    if status is not None:
        consulta = consulta.where(EmailOutbox.status == status)
    if tipo is not None:
        consulta = consulta.where(EmailOutbox.tipo == tipo)
    if destinatario:
        consulta = consulta.where(
            func.lower(col(EmailOutbox.destinatario_email)) == destinatario.lower()
        )
    return list((await db.exec(consulta)).all())


async def esgotar_reservas_vencidas(db: AsyncSession) -> int:
    """Reserva vencida de um e-mail que já gastou todas as tentativas: o worker caiu no meio
    do envio. Não há mais o que tentar, então vai para FALHA (e pode ser reenviado à mão)."""
    comando = (
        update(EmailOutbox)
        .where(
            EmailOutbox.status == StatusEmail.ENVIANDO,
            col(EmailOutbox.reservado_ate) <= AGORA_UTC,
            EmailOutbox.tentativas >= EmailOutbox.max_tentativas,
        )
        .values(
            status=StatusEmail.FALHA,
            reservado_ate=None,
            ultimo_erro="O envio não terminou e as tentativas acabaram.",
            atualizado_em=AGORA_UTC,
        )
    )
    return (await db.exec(comando)).rowcount


async def reservar_emails(db: AsyncSession, *, limite: int, reserva_segundos: int) -> list[dict]:
    """Pega até `limite` e-mails prontos para envio e os reserva para este worker.

    Pronto é PENDENTE com a hora da próxima tentativa vencida, ou ENVIANDO com a reserva vencida
    (worker que caiu). `FOR UPDATE SKIP LOCKED` faz dois workers nunca pegarem o mesmo e-mail.
    A seleção é materializada antes do UPDATE: o otimizador não pode reexecutar o LIMIT
    para cada linha modificada. Cada reserva conta como uma tentativa."""
    resultado = await db.exec(
        text(
            """
            WITH candidatos AS MATERIALIZED (
                SELECT id FROM emails_outbox
                WHERE cancelado_em IS NULL AND (
                    (status = 'PENDENTE' AND proxima_tentativa_em <= (now() AT TIME ZONE 'utc'))
                    OR (status = 'ENVIANDO' AND reservado_ate <= (now() AT TIME ZONE 'utc'))
                )
                ORDER BY proxima_tentativa_em, criado_em, id
                LIMIT :limite
                FOR UPDATE SKIP LOCKED
            ), reservados AS (
                UPDATE emails_outbox AS email SET
                    status = 'ENVIANDO',
                    tentativas = email.tentativas + 1,
                    reservado_ate = (now() AT TIME ZONE 'utc') + make_interval(secs => :reserva),
                    atualizado_em = (now() AT TIME ZONE 'utc')
                FROM candidatos
                WHERE email.id = candidatos.id
                RETURNING email.id, email.tipo, email.destinatario_email,
                          email.destinatario_nome, email.assunto, email.corpo_texto,
                          email.corpo_html, email.tentativas, email.max_tentativas,
                          email.chave_idempotencia, email.proxima_tentativa_em, email.criado_em
            )
            SELECT id, tipo, destinatario_email, destinatario_nome, assunto,
                   corpo_texto, corpo_html, tentativas, max_tentativas, chave_idempotencia
            FROM reservados
            ORDER BY proxima_tentativa_em, criado_em, id
            """
        ).bindparams(reserva=reserva_segundos, limite=limite)
    )
    return [dict(linha) for linha in resultado.mappings().all()]


async def registrar_envio(db: AsyncSession, email_id: UUID, provedor_mensagem_id: str | None):
    """O provedor aceitou: guarda a hora e apaga o corpo, que pode ter links de acesso."""
    await db.exec(
        update(EmailOutbox)
        .where(EmailOutbox.id == email_id)
        .values(
            status=StatusEmail.ENVIADO,
            enviado_em=AGORA_UTC,
            provedor_mensagem_id=provedor_mensagem_id,
            corpo_texto=None,
            corpo_html=None,
            reservado_ate=None,
            ultimo_erro=None,
            atualizado_em=AGORA_UTC,
        )
    )


async def registrar_nova_tentativa(
    db: AsyncSession, email_id: UUID, erro: str, espera_segundos: int
) -> None:
    await db.exec(
        text(
            """
            UPDATE emails_outbox SET
                status = 'PENDENTE',
                reservado_ate = NULL,
                ultimo_erro = :erro,
                proxima_tentativa_em = (now() AT TIME ZONE 'utc') + make_interval(secs => :espera),
                atualizado_em = (now() AT TIME ZONE 'utc')
            WHERE id = :id
            """
        ).bindparams(id=email_id, erro=erro, espera=espera_segundos)
    )


async def registrar_falha(db: AsyncSession, email_id: UUID, erro: str) -> None:
    await db.exec(
        update(EmailOutbox)
        .where(EmailOutbox.id == email_id)
        .values(
            status=StatusEmail.FALHA,
            reservado_ate=None,
            ultimo_erro=erro,
            atualizado_em=AGORA_UTC,
        )
    )


async def recolocar_na_fila(db: AsyncSession, email: EmailOutbox) -> EmailOutbox:
    """Reenvio manual de um e-mail em FALHA: zera as tentativas e libera para o worker."""
    await db.exec(
        update(EmailOutbox)
        .where(EmailOutbox.id == email.id)
        .values(
            status=StatusEmail.PENDENTE,
            tentativas=0,
            proxima_tentativa_em=AGORA_UTC,
            reservado_ate=None,
            atualizado_em=AGORA_UTC,
        )
    )
    await db.refresh(email)
    return email


async def cancelar_aviso_pendente(db: AsyncSession, chave: str) -> bool:
    """Retira da fila o aviso de `chave` que o worker ainda não pegou (sem commit). Só o que está
    `PENDENTE` é cancelado; reservado (`ENVIANDO`), `ENVIADO` ou em `FALHA` fica como está e a
    chamada não faz nada. O corpo é descartado, então o token antigo some da tabela. O UPDATE
    condicional e o `FOR UPDATE SKIP LOCKED` do worker não se pisam: quem chega depois vê o
    estado do outro. Devolve se cancelou."""
    cancelado = await db.exec(
        update(EmailOutbox)
        .where(
            EmailOutbox.chave_idempotencia == chave,
            EmailOutbox.status == StatusEmail.PENDENTE,
            col(EmailOutbox.cancelado_em).is_(None),
        )
        .values(
            status=StatusEmail.FALHA,
            cancelado_em=AGORA_UTC,
            reservado_ate=None,
            corpo_texto=None,
            corpo_html=None,
            ultimo_erro="Aviso substituído por um reenvio ou pela troca do e-mail do convite.",
            atualizado_em=AGORA_UTC,
        )
        .returning(col(EmailOutbox.id))
    )
    return cancelado.first() is not None
