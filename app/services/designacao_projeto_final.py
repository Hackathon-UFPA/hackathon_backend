"""BE-S6-09: designação dos projetos finais ao Comitê Técnico (RF47, RF48, RN11, RN13, Q07).

Projeto final = proposta aprovada na homologação do resultado científico (RF31). Segue o padrão
da distribuição das propostas (BE-S4-09), mas em tabelas próprias: não se mistura com a
avaliação científica. Diferenças:
- só Comitê Técnico é elegível;
- integrantes da equipe, mentores (atuais ou anteriores) e conflitos declarados ficam impedidos;
- a redistribuição não apaga: marca a designação como removida (histórico auditável).

Quando a avaliação técnica existir (BE-S6-10), distribuir deve pular projetos com avaliação
iniciada e redistribuir deve recusá-los, como em `designacao_avaliacao`.
"""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import StatusHackathon
from app.controllers.designacao_projeto_final import (
    adicionar,
    carga_por_avaliador,
    contar_tecnicos_entre,
    existe_vigente,
    get_avaliador_tecnico,
    get_conflito,
    get_equipe_do_hackathon,
    get_projeto_designado,
    get_projeto_final,
    impedidos_por_equipe,
    listar_avaliadores_tecnicos,
    listar_conflitos,
    listar_projetos_designados,
    listar_projetos_finais,
    listar_usuarios_por_id,
    listar_vigentes_do_hackathon,
    listar_vigentes_do_projeto,
    marcar_removida,
)
from app.controllers.hackathon import get_hackathon_para_atualizar
from app.controllers.resultado import get_homologacao
from app.exceptions.convite import hackathon_nao_encontrado
from app.exceptions.db import erro_de_integridade_sql
from app.exceptions.projeto_final import (
    avaliador_em_conflito,
    avaliador_tecnico_nao_encontrado,
    avaliadores_tecnicos_insuficientes,
    avaliadores_tecnicos_nao_elegiveis,
    conflito_com_designacao_vigente,
    conflito_ja_registrado,
    equipe_nao_encontrada_no_hackathon,
    hackathon_encerrado,
    projeto_final_nao_encontrado,
    quantidade_de_avaliadores_tecnicos_invalida,
    quantidade_tecnica_nao_configurada,
    resultado_cientifico_nao_homologado,
)
from app.models import (
    ConflitoProjetoFinal,
    DesignacaoProjetoFinal,
    Hackathon,
    ResultadoProposta,
    Submissao,
    Usuario,
)
from app.schemas.designacao_projeto_final import (
    AvaliadorTecnicoDesignadoResponse,
    ConfiguracaoAvaliacaoTecnicaResponse,
    DistribuicaoProjetosFinaisResponse,
    ProjetoFinalDesignadoAdminResponse,
)

STATUS_ENCERRADOS = {StatusHackathon.FINALIZADO, StatusHackathon.CANCELADO}


async def _hackathon_travado(db: AsyncSession, hackathon_id: UUID) -> Hackathon:
    """Trava a linha do hackathon: serializa distribuições, redistribuições e conflitos."""
    hackathon = await get_hackathon_para_atualizar(db, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    if hackathon.status in STATUS_ENCERRADOS:
        hackathon_encerrado()
    return hackathon


def _exigir_quantidade(hackathon: Hackathon) -> int:
    if hackathon.avaliadores_por_projeto_final is None:
        quantidade_tecnica_nao_configurada()
    return hackathon.avaliadores_por_projeto_final


async def _projetos(db: AsyncSession, hackathon_id: UUID) -> list[ResultadoProposta]:
    homologacao = await get_homologacao(db, hackathon_id)
    if homologacao is None:
        resultado_cientifico_nao_homologado()
    return await listar_projetos_finais(db, homologacao.id)


async def configurar(
    db: AsyncSession, hackathon_id: UUID, quantidade: int
) -> ConfiguracaoAvaliacaoTecnicaResponse:
    """Só define o N das próximas distribuições; designações existentes ficam como estão."""
    try:
        hackathon = await _hackathon_travado(db, hackathon_id)
        hackathon.avaliadores_por_projeto_final = quantidade
        db.add(hackathon)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return ConfiguracaoAvaliacaoTecnicaResponse(
        hackathon_id=hackathon_id, avaliadores_por_projeto_final=quantidade
    )


async def distribuir(
    db: AsyncSession, organizador: Usuario, hackathon_id: UUID
) -> DistribuicaoProjetosFinaisResponse:
    """Completa até N avaliadores cada projeto final, sempre com quem tem menos projetos e sem
    ninguém impedido (RN13). Se faltar avaliador para qualquer projeto, nada é gravado."""
    try:
        hackathon = await _hackathon_travado(db, hackathon_id)
        n = _exigir_quantidade(hackathon)
        projetos = await _projetos(db, hackathon.id)

        existentes: dict[UUID, set[UUID]] = {p.submissao_id: set() for p in projetos}
        for designacao in await listar_vigentes_do_hackathon(db, hackathon.id):
            existentes.setdefault(designacao.submissao_id, set()).add(designacao.avaliador_id)
        impedidos = await impedidos_por_equipe(db, hackathon.id, [p.equipe_id for p in projetos])
        elegiveis = [u.id for u in await listar_avaliadores_tecnicos(db, hackathon.organizacao_id)]
        carga = await carga_por_avaliador(db, hackathon.id)

        novas: list[DesignacaoProjetoFinal] = []
        completos = 0
        distribuidos = 0
        for projeto in projetos:
            ja_designados = existentes[projeto.submissao_id]
            faltam = n - len(ja_designados)
            if faltam <= 0:
                completos += 1
                continue
            bloqueados = ja_designados | impedidos.get(projeto.equipe_id, set())
            candidatos = sorted(
                (id_ for id_ in elegiveis if id_ not in bloqueados),
                key=lambda id_: (carga.get(id_, 0), str(id_)),
            )
            if len(candidatos) < faltam:
                avaliadores_tecnicos_insuficientes(
                    n, projeto.submissao_id, len(candidatos) + len(ja_designados)
                )
            for avaliador_id in candidatos[:faltam]:
                carga[avaliador_id] = carga.get(avaliador_id, 0) + 1
                novas.append(
                    DesignacaoProjetoFinal(
                        submissao_id=projeto.submissao_id,
                        equipe_id=projeto.equipe_id,
                        hackathon_id=hackathon.id,
                        avaliador_id=avaliador_id,
                        atribuido_por=organizador.id,
                    )
                )
            distribuidos += 1

        for designacao in novas:
            adicionar(db, designacao)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return DistribuicaoProjetosFinaisResponse(
        hackathon_id=hackathon_id,
        avaliadores_por_projeto_final=n,
        projetos_distribuidos=distribuidos,
        designacoes_criadas=len(novas),
        projetos_ja_completos=completos,
    )


async def redistribuir(
    db: AsyncSession, organizador: Usuario, submissao_id: UUID, avaliador_ids: list[UUID]
) -> ProjetoFinalDesignadoAdminResponse:
    """Troca os avaliadores do projeto pela lista informada (exatamente N, sem repetidos, sem
    impedidos). Quem continua mantém a designação; quem sai fica registrado como removido."""
    try:
        projeto = await get_projeto_final(db, submissao_id)
        if projeto is None:
            projeto_final_nao_encontrado()
        hackathon = await _hackathon_travado(db, projeto.hackathon_id)
        n = _exigir_quantidade(hackathon)
        if len(set(avaliador_ids)) != len(avaliador_ids) or len(avaliador_ids) != n:
            quantidade_de_avaliadores_tecnicos_invalida(n)
        if await contar_tecnicos_entre(db, avaliador_ids, hackathon.organizacao_id) != n:
            avaliadores_tecnicos_nao_elegiveis()
        impedidos = (await impedidos_por_equipe(db, hackathon.id, [projeto.equipe_id])).get(
            projeto.equipe_id, set()
        )
        em_conflito = [id_ for id_ in avaliador_ids if id_ in impedidos]
        if em_conflito:
            avaliador_em_conflito(em_conflito)

        atuais = {d.avaliador_id: d for d in await listar_vigentes_do_projeto(db, submissao_id)}
        for avaliador_id, designacao in atuais.items():
            if avaliador_id not in avaliador_ids:
                marcar_removida(db, designacao, organizador.id)
        # A remoção precisa chegar ao banco antes dos inserts, por causa do índice parcial
        await db.flush()
        for avaliador_id in avaliador_ids:
            if avaliador_id not in atuais:
                adicionar(
                    db,
                    DesignacaoProjetoFinal(
                        submissao_id=projeto.submissao_id,
                        equipe_id=projeto.equipe_id,
                        hackathon_id=hackathon.id,
                        avaliador_id=avaliador_id,
                        atribuido_por=organizador.id,
                    ),
                )
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    return (await _agrupar(db, hackathon.id, [projeto]))[0]


async def _agrupar(
    db: AsyncSession, hackathon_id: UUID, projetos: list[ResultadoProposta]
) -> list[ProjetoFinalDesignadoAdminResponse]:
    designacoes = await listar_vigentes_do_hackathon(db, hackathon_id)
    usuarios = await listar_usuarios_por_id(db, list({d.avaliador_id for d in designacoes}))
    por_projeto: dict[UUID, list[AvaliadorTecnicoDesignadoResponse]] = {}
    for designacao in designacoes:
        usuario = usuarios[designacao.avaliador_id]
        por_projeto.setdefault(designacao.submissao_id, []).append(
            AvaliadorTecnicoDesignadoResponse(
                id=usuario.id,
                nome=usuario.nome,
                email=usuario.email,
                atribuido_em=designacao.atribuido_em,
            )
        )
    return [
        ProjetoFinalDesignadoAdminResponse(
            submissao_id=projeto.submissao_id,
            equipe_id=projeto.equipe_id,
            titulo=projeto.titulo,
            avaliadores=por_projeto.get(projeto.submissao_id, []),
        )
        for projeto in projetos
    ]


async def listar_designacoes(
    db: AsyncSession, hackathon_id: UUID
) -> list[ProjetoFinalDesignadoAdminResponse]:
    """Cada projeto final com os avaliadores vigentes (lista vazia se ainda não há)."""
    hackathon = await db.get(Hackathon, hackathon_id)
    if hackathon is None:
        hackathon_nao_encontrado()
    return await _agrupar(db, hackathon_id, await _projetos(db, hackathon_id))


async def registrar_conflito(
    db: AsyncSession,
    organizador: Usuario,
    hackathon_id: UUID,
    equipe_id: UUID,
    avaliador_id: UUID,
    motivo: str,
) -> ConflitoProjetoFinal:
    """RN13: o avaliador deixa de poder ser designado ao projeto da equipe."""
    try:
        hackathon = await _hackathon_travado(db, hackathon_id)
        if await get_equipe_do_hackathon(db, equipe_id, hackathon.id) is None:
            equipe_nao_encontrada_no_hackathon()
        if await get_avaliador_tecnico(db, avaliador_id, hackathon.organizacao_id) is None:
            avaliador_tecnico_nao_encontrado()
        if await get_conflito(db, equipe_id, avaliador_id) is not None:
            conflito_ja_registrado()
        if await existe_vigente(db, equipe_id, avaliador_id):
            conflito_com_designacao_vigente()
        conflito = ConflitoProjetoFinal(
            hackathon_id=hackathon.id,
            equipe_id=equipe_id,
            avaliador_id=avaliador_id,
            motivo=motivo,
            registrado_por=organizador.id,
        )
        adicionar(db, conflito)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        erro_de_integridade_sql(error)
    except Exception:
        await db.rollback()
        raise
    await db.refresh(conflito)
    return conflito


async def consultar_conflitos(db: AsyncSession, hackathon_id: UUID) -> list[ConflitoProjetoFinal]:
    if await db.get(Hackathon, hackathon_id) is None:
        hackathon_nao_encontrado()
    return await listar_conflitos(db, hackathon_id)


async def listar_meus_projetos(db: AsyncSession, avaliador: Usuario) -> list[Submissao]:
    return await listar_projetos_designados(db, avaliador.id)


async def consultar_meu_projeto(
    db: AsyncSession, avaliador: Usuario, submissao_id: UUID
) -> Submissao:
    """Projeto não designado a quem consulta 'não existe': não revela projetos alheios."""
    projeto = await get_projeto_designado(db, submissao_id, avaliador.id)
    if projeto is None:
        projeto_final_nao_encontrado()
    return projeto
