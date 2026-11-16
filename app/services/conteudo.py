"""Conteúdo institucional da edição (BE-S5-12): apoiadores, FAQ, cronograma e página pública.

Todo conteúdo nasce não publicado e só aparece nas rotas públicas depois de `publicado = true`.
Quem acrescenta ou reordena itens trava a linha da edição (FOR UPDATE): a posição `ordem` é
calculada lendo o maior valor, então duas escritas simultâneas se enfileiram e nunca repetem a
posição nem se perdem."""

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon, TipoTermo
from app.controllers.conteudo import (
    get_item,
    listar_itens,
    proxima_ordem,
    remover_item,
    salvar_item,
)
from app.controllers.equipe import get_hackathon_by_id
from app.controllers.hackathon import get_hackathon_para_atualizar
from app.controllers.termo import get_termo_vigente
from app.exceptions.conteudo import conflito_de_conteudo, conteudo_invalido, item_nao_encontrado
from app.exceptions.convite import hackathon_nao_encontrado
from app.models import Apoiador, FaqItem, FaseCronograma, Hackathon
from app.schemas.conteudo import (
    ApoiadorCreate,
    ApoiadoresPorCategoria,
    ApoiadorPublico,
    ApoiadorUpdate,
    FaqCreate,
    FaqPublico,
    FaqUpdate,
    FaseCreate,
    FaseCronogramaResponse,
    FaseUpdate,
    HackathonPublico,
    PaginaPublicaResponse,
    RegulamentoPublico,
)
from app.validations.inscricao import como_utc, inscricoes_abertas

# Datas do próprio edital que viram linhas do cronograma, sem duplicar o cadastro (RF13, RF59):
# (nome, campo de início, campo de fim)
FASES_DO_EDITAL = (
    ("Inscrições", "inscricoes_inicio", "inscricoes_fim"),
    ("Homologação das equipes", "inscricoes_fim", "homologacao_fim"),
    ("Envio de propostas", "propostas_inicio", "propostas_fim"),
    ("Evento", "data_inicio", "data_fim"),
)


def agora_utc() -> datetime:
    return datetime.now(UTC)


async def edicao(db: AsyncSession, hackathon_id: UUID, *, travar: bool = False) -> Hackathon:
    """A edição, ou 404. Com `travar`, a linha fica bloqueada até o fim da transação."""
    busca = get_hackathon_para_atualizar if travar else get_hackathon_by_id
    hackathon = await busca(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    return hackathon


async def edicao_publica(db: AsyncSession, hackathon_id: UUID) -> Hackathon:
    """Edição visível ao público: uma edição em RASCUNHO ainda não foi divulgada (404)."""
    hackathon = await edicao(db, hackathon_id)
    if hackathon.status == StatusHackathon.RASCUNHO:
        hackathon_nao_encontrado()
    return hackathon


async def _salvar(db: AsyncSession, item):
    await salvar_item(db, item)
    await db.commit()
    await db.refresh(item)
    return item


async def _editar(db: AsyncSession, modelo, nome: str, hackathon_id, item_id, valores, validar):
    await edicao(db, hackathon_id)
    item = await get_item(db, modelo, hackathon_id, item_id, bloquear=True)
    if item is None:
        item_nao_encontrado(nome)
    for campo, valor in valores.items():
        setattr(item, campo, valor)
    item.atualizado_em = agora_utc()
    if validar is not None:
        validar(item)
    return await _salvar(db, item)


async def _excluir(db: AsyncSession, modelo, nome: str, hackathon_id, item_id) -> None:
    await edicao(db, hackathon_id)
    item = await get_item(db, modelo, hackathon_id, item_id, bloquear=True)
    if item is None:
        item_nao_encontrado(nome)
    await remover_item(db, item)
    await db.commit()


# --- Apoiadores (RF14) ---


async def criar_apoiador(db: AsyncSession, hackathon_id: UUID, dados: ApoiadorCreate) -> Apoiador:
    await edicao(db, hackathon_id, travar=True)
    item = Apoiador(hackathon_id=hackathon_id, **dados.model_dump())
    item.ordem = await proxima_ordem(db, Apoiador, hackathon_id)
    return await _salvar(db, item)


async def listar_apoiadores(
    db: AsyncSession,
    hackathon_id: UUID,
    *,
    publicado: bool | None,
    categoria: str | None,
    limite: int,
    deslocamento: int,
) -> list[Apoiador]:
    await edicao(db, hackathon_id)
    filtros = []
    if publicado is not None:
        filtros.append(Apoiador.publicado == publicado)
    if categoria:
        filtros.append(Apoiador.categoria == categoria)
    return await listar_itens(
        db,
        Apoiador,
        hackathon_id,
        filtros=tuple(filtros),
        ordem=(Apoiador.ordem, Apoiador.criado_em, Apoiador.id),
        limite=limite,
        deslocamento=deslocamento,
    )


async def editar_apoiador(
    db: AsyncSession, hackathon_id: UUID, apoiador_id: UUID, dados: ApoiadorUpdate
) -> Apoiador:
    valores = dados.model_dump(exclude_unset=True)
    return await _editar(db, Apoiador, "Apoiador", hackathon_id, apoiador_id, valores, None)


async def excluir_apoiador(db: AsyncSession, hackathon_id: UUID, apoiador_id: UUID) -> None:
    await _excluir(db, Apoiador, "Apoiador", hackathon_id, apoiador_id)


# --- FAQ (RF12) ---


async def criar_faq(db: AsyncSession, hackathon_id: UUID, dados: FaqCreate) -> FaqItem:
    await edicao(db, hackathon_id, travar=True)
    item = FaqItem(hackathon_id=hackathon_id, **dados.model_dump())
    item.ordem = await proxima_ordem(db, FaqItem, hackathon_id)
    return await _salvar(db, item)


async def listar_faq(
    db: AsyncSession,
    hackathon_id: UUID,
    *,
    publicado: bool | None,
    limite: int,
    deslocamento: int,
) -> list[FaqItem]:
    await edicao(db, hackathon_id)
    filtros = () if publicado is None else (FaqItem.publicado == publicado,)
    return await listar_itens(
        db,
        FaqItem,
        hackathon_id,
        filtros=filtros,
        ordem=(FaqItem.ordem, FaqItem.criado_em, FaqItem.id),
        limite=limite,
        deslocamento=deslocamento,
    )


async def editar_faq(
    db: AsyncSession, hackathon_id: UUID, item_id: UUID, dados: FaqUpdate
) -> FaqItem:
    valores = dados.model_dump(exclude_unset=True)
    return await _editar(db, FaqItem, "Pergunta", hackathon_id, item_id, valores, None)


async def excluir_faq(db: AsyncSession, hackathon_id: UUID, item_id: UUID) -> None:
    await _excluir(db, FaqItem, "Pergunta", hackathon_id, item_id)


async def reordenar_faq(db: AsyncSession, hackathon_id: UUID, ids: list[UUID]) -> list[FaqItem]:
    """Define a nova ordem de todas as perguntas da edição. A lista precisa ter exatamente as
    perguntas atuais: se alguém acrescentou ou excluiu uma no meio do caminho, é 409 e a
    interface recarrega, em vez de gravar uma ordem que já não vale."""
    await edicao(db, hackathon_id, travar=True)
    itens = await listar_itens(
        db, FaqItem, hackathon_id, ordem=(FaqItem.ordem, FaqItem.criado_em, FaqItem.id)
    )
    por_id = {item.id: item for item in itens}
    if set(ids) != set(por_id):
        conflito_de_conteudo(
            "A lista precisa trazer exatamente as perguntas atuais da edição: recarregue e tente "
            "de novo."
        )
    agora = agora_utc()
    novos = []
    for posicao, item_id in enumerate(ids):
        item = por_id[item_id]
        if item.ordem != posicao:
            item.ordem = posicao
            item.atualizado_em = agora
            db.add(item)
        novos.append(item)
    await db.commit()
    return novos


# --- Cronograma (RF13, RF59) ---


def _validar_fase(fase: FaseCronograma) -> None:
    if como_utc(fase.fim) < como_utc(fase.inicio):
        conteudo_invalido("fim não pode ser antes de inicio.")


async def criar_fase(db: AsyncSession, hackathon_id: UUID, dados: FaseCreate) -> FaseCronograma:
    await edicao(db, hackathon_id)
    return await _salvar(db, FaseCronograma(hackathon_id=hackathon_id, **dados.model_dump()))


async def editar_fase(
    db: AsyncSession, hackathon_id: UUID, fase_id: UUID, dados: FaseUpdate
) -> FaseCronograma:
    valores = dados.model_dump(exclude_unset=True)
    return await _editar(db, FaseCronograma, "Fase", hackathon_id, fase_id, valores, _validar_fase)


async def excluir_fase(db: AsyncSession, hackathon_id: UUID, fase_id: UUID) -> None:
    await _excluir(db, FaseCronograma, "Fase", hackathon_id, fase_id)


def _situacao(inicio: datetime, fim: datetime, agora: datetime) -> str:
    if agora < inicio:
        return "NAO_INICIADA"
    return "EM_ANDAMENTO" if agora <= fim else "ENCERRADA"


def linha_do_tempo(
    hackathon: Hackathon,
    fases: list[FaseCronograma],
    *,
    so_publicadas: bool,
    agora: datetime | None = None,
) -> list[FaseCronogramaResponse]:
    """Cronograma em ordem cronológica, com as datas do edital e as fases cadastradas. A fase
    em andamento vem com `atual = true`. O edital continua a fonte das datas dele: mudar o
    `hackathon` muda o cronograma, sem cadastro duplicado."""
    agora = como_utc(agora or agora_utc())
    linhas = []
    for nome, campo_inicio, campo_fim in FASES_DO_EDITAL:
        inicio, fim = getattr(hackathon, campo_inicio), getattr(hackathon, campo_fim)
        if inicio is None or fim is None:
            continue
        inicio, fim = como_utc(inicio), como_utc(fim)
        situacao = _situacao(inicio, fim, agora)
        linhas.append(
            FaseCronogramaResponse(
                origem="EDITAL",
                nome=nome,
                inicio=inicio,
                fim=fim,
                situacao=situacao,
                atual=situacao == "EM_ANDAMENTO",
            )
        )
    for fase in fases:
        if so_publicadas and not fase.publicado:
            continue
        inicio, fim = como_utc(fase.inicio), como_utc(fase.fim)
        situacao = _situacao(inicio, fim, agora)
        linhas.append(
            FaseCronogramaResponse(
                id=fase.id,
                origem="PERSONALIZADA",
                nome=fase.nome,
                descricao=fase.descricao,
                inicio=inicio,
                fim=fim,
                publicado=fase.publicado,
                situacao=situacao,
                atual=situacao == "EM_ANDAMENTO",
            )
        )
    return sorted(linhas, key=lambda linha: (linha.inicio, linha.fim, linha.nome))


async def cronograma_da_edicao(
    db: AsyncSession, hackathon: Hackathon, *, so_publicadas: bool
) -> list[FaseCronogramaResponse]:
    fases = await listar_itens(db, FaseCronograma, hackathon.id)
    return linha_do_tempo(hackathon, fases, so_publicadas=so_publicadas)


async def cronograma_admin(db: AsyncSession, hackathon_id: UUID) -> list[FaseCronogramaResponse]:
    return await cronograma_da_edicao(db, await edicao(db, hackathon_id), so_publicadas=False)


# --- Página pública (RF10 a RF14) ---

CAMPOS_PUBLICOS = (
    "id",
    "nome",
    "tema",
    "descricao",
    "status",
    "data_inicio",
    "data_fim",
    "inscricoes_inicio",
    "inscricoes_fim",
    "homologacao_fim",
    "propostas_inicio",
    "propostas_fim",
)


def _publico(hackathon: Hackathon) -> dict:
    dados = {campo: getattr(hackathon, campo) for campo in CAMPOS_PUBLICOS}
    return {**dados, "inscricoes_abertas": inscricoes_abertas(hackathon)}


async def listar_edicoes_publicas(
    db: AsyncSession, limite: int, deslocamento: int
) -> list[HackathonPublico]:
    """Edições já divulgadas (todas menos RASCUNHO), das mais recentes às mais antigas."""
    consulta = (
        select(Hackathon)
        .where(col(Hackathon.status) != StatusHackathon.RASCUNHO)
        .order_by(col(Hackathon.data_inicio).desc().nulls_last(), Hackathon.nome, Hackathon.id)
        .limit(limite)
        .offset(deslocamento)
    )
    return [HackathonPublico(**_publico(h)) for h in (await db.exec(consulta)).all()]


async def faq_publico(db: AsyncSession, hackathon_id: UUID) -> list[FaqPublico]:
    await edicao_publica(db, hackathon_id)
    itens = await listar_itens(
        db,
        FaqItem,
        hackathon_id,
        filtros=(col(FaqItem.publicado).is_(True),),
        ordem=(FaqItem.ordem, FaqItem.criado_em, FaqItem.id),
    )
    return [FaqPublico.model_validate(item) for item in itens]


async def apoiadores_publicos(db: AsyncSession, hackathon_id: UUID) -> list[ApoiadoresPorCategoria]:
    """Só os publicados, agrupados por categoria. As categorias seguem a posição do primeiro
    apoiador de cada uma."""
    await edicao_publica(db, hackathon_id)
    itens = await listar_itens(
        db,
        Apoiador,
        hackathon_id,
        filtros=(col(Apoiador.publicado).is_(True),),
        ordem=(Apoiador.ordem, Apoiador.criado_em, Apoiador.id),
    )
    grupos: dict[str, list[ApoiadorPublico]] = {}
    for item in itens:
        grupos.setdefault(item.categoria, []).append(ApoiadorPublico.model_validate(item))
    return [ApoiadoresPorCategoria(categoria=c, apoiadores=a) for c, a in grupos.items()]


async def cronograma_publico(db: AsyncSession, hackathon_id: UUID) -> list[FaseCronogramaResponse]:
    hackathon = await edicao_publica(db, hackathon_id)
    return await cronograma_da_edicao(db, hackathon, so_publicadas=True)


async def regulamento_vigente(db: AsyncSession, hackathon_id: UUID) -> RegulamentoPublico | None:
    termo = await get_termo_vigente(db, hackathon_id, TipoTermo.REGULAMENTO)
    return RegulamentoPublico.model_validate(termo) if termo else None


async def regulamento_publico(db: AsyncSession, hackathon_id: UUID) -> RegulamentoPublico:
    await edicao_publica(db, hackathon_id)
    regulamento = await regulamento_vigente(db, hackathon_id)
    if regulamento is None:
        item_nao_encontrado("Regulamento publicado")
    return regulamento


async def pagina_publica(db: AsyncSession, hackathon_id: UUID) -> PaginaPublicaResponse:
    hackathon = await edicao_publica(db, hackathon_id)
    return PaginaPublicaResponse(
        **_publico(hackathon),
        regulamento=await regulamento_vigente(db, hackathon_id),
        faq=await faq_publico(db, hackathon_id),
        cronograma=await cronograma_da_edicao(db, hackathon, so_publicadas=True),
        apoiadores=await apoiadores_publicos(db, hackathon_id),
    )
