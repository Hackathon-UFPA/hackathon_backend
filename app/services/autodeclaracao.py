"""Autodeclaração de vínculo da própria pessoa (BE-S5-03; RF01, RF20 a RF23, RN05, RN25).

Declarar não comprova nada: a autodeclaração é o que a pessoa afirma, e o vínculo só está
comprovado quando o comprovante do tipo certo é aprovado por um conferente. As duas coisas ficam
em tabelas separadas e a resposta nunca mistura uma com a outra. Só o próprio usuário declara; não
existe rota, nem campo, para declarar em nome de outra pessoa.
"""

from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import PapelUsuario, StatusComprovante, TipoIntegrante
from app.controllers.autodeclaracao import (
    criar_autodeclaracao,
    listar_autodeclaracoes,
    travar_usuario,
)
from app.controllers.comprovante_vinculo import get_ultimo_comprovante
from app.controllers.membro_equipe import get_membro_no_hackathon
from app.exceptions.auth import acesso_negado
from app.models import AutodeclaracaoVinculo, Usuario
from app.schemas.autodeclaracao import (
    AutodeclaracaoEnvio,
    AutodeclaracaoResponse,
    AutodeclaracaoSituacaoResponse,
    ComprovacaoResumo,
)
from app.services.edicao_participante import resolver_edicao
from app.services.inscricao import reavaliar_equipe_do_usuario

# Quem declara vínculo é quem participa. DEV segue a exceção do time de desenvolvimento.
PAPEIS_QUE_DECLARAM = (PapelUsuario.PARTICIPANTE, PapelUsuario.DEV)

CAMPOS = ("tipo", "instituicao", "curso", "periodo", "organizacao", "cargo")


def _exigir_participante(usuario: Usuario) -> None:
    if usuario.papel not in PAPEIS_QUE_DECLARAM:
        acesso_negado()


def _igual(declaracao: AutodeclaracaoVinculo, dados: AutodeclaracaoEnvio) -> bool:
    return all(getattr(declaracao, campo) == getattr(dados, campo) for campo in CAMPOS)


async def declarar(
    db: AsyncSession, usuario: Usuario, dados: AutodeclaracaoEnvio, hackathon_id: UUID | None = None
) -> AutodeclaracaoVinculo:
    """Registra a declaração de quem está logado. Cada mudança é uma linha nova (auditoria); repetir
    a declaração atual não grava nada. A equipe da pessoa é reavaliada: uma declaração que
    contradiz o tipo indicado pelo líder tira a equipe da homologação até alguém corrigir."""
    _exigir_participante(usuario)
    hackathon = await resolver_edicao(db, hackathon_id)
    try:
        # Declarações simultâneas da mesma pessoa se serializam, e duas iguais viram uma só
        await travar_usuario(db, usuario.id)
        historico = await listar_autodeclaracoes(db, usuario.id, hackathon.id)
        if historico and _igual(historico[0], dados):
            return historico[0]
        declaracao = AutodeclaracaoVinculo(
            usuario_id=usuario.id, hackathon_id=hackathon.id, **dados.model_dump()
        )
        criar_autodeclaracao(db, declaracao)
        await db.flush()
        await reavaliar_equipe_do_usuario(db, hackathon.id, usuario.id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(declaracao)
    return declaracao


async def situacao(
    db: AsyncSession, usuario: Usuario, hackathon_id: UUID | None = None
) -> AutodeclaracaoSituacaoResponse:
    """A declaração atual e o histórico, ao lado da comprovação: o que a pessoa afirma e o que
    foi verificado. Não traz o link do documento, que é privado."""
    _exigir_participante(usuario)
    hackathon = await resolver_edicao(db, hackathon_id, exigir_inscricoes=False)
    historico = await listar_autodeclaracoes(db, usuario.id, hackathon.id)
    atual = historico[0] if historico else None
    membro = await get_membro_no_hackathon(db, hackathon.id, usuario.id)
    indicado = membro.tipo_integrante if membro else None
    # O vínculo que vale é o que o líder indicou, se a pessoa já está em uma equipe; senão o
    # que ela declarou; senão o acadêmico, como antes da BE-S5-03
    tipo = indicado or (atual.tipo if atual else TipoIntegrante.ESTUDANTE)
    comprovante = await get_ultimo_comprovante(db, usuario.id, hackathon.id, tipo)
    exigido = (
        hackathon.exige_comprovante_profissional
        if tipo == TipoIntegrante.PROFISSIONAL
        else hackathon.exige_comprovante_estudante
    )
    return AutodeclaracaoSituacaoResponse(
        hackathon_id=hackathon.id,
        atual=AutodeclaracaoResponse.model_validate(atual) if atual else None,
        historico=[AutodeclaracaoResponse.model_validate(d) for d in historico],
        tipo_indicado_pelo_lider=indicado,
        comprovante=ComprovacaoResumo.model_validate(comprovante) if comprovante else None,
        vinculo_comprovado=bool(comprovante and comprovante.status == StatusComprovante.APROVADO),
        autodeclaracao_exigida=hackathon.exige_autodeclaracao,
        comprovante_exigido=exigido,
    )
