"""Desempates finais da classificação e independência do contexto decimal."""

from datetime import datetime
from decimal import ROUND_DOWN, Decimal, localcontext
from uuid import UUID, uuid4

import pytest

from app.services.resultado import _classificar, _Consolidado, media_das_notas


def proposta(id_, enviado_em=None, notas=("8",), aprovacoes=2):
    return _Consolidado(
        submissao_id=UUID(int=id_),
        equipe_id=uuid4(),
        equipe_nome=None,
        tema_titulo=None,
        titulo=None,
        enviado_em=enviado_em,
        notas=[Decimal(nota) for nota in notas],
        aprovacao=aprovacoes,
    )


def test_empate_em_media_e_recomendacoes_prioriza_envio_mais_antigo():
    antiga = proposta(2, datetime(2026, 11, 1))
    recente = proposta(1, datetime(2026, 11, 2))

    _classificar([recente, antiga])

    assert antiga.classificacao == 1
    assert recente.classificacao == 2


@pytest.mark.parametrize("ordem", [(3, 1, 2), (2, 3, 1), (1, 2, 3)])
def test_empate_completo_e_resolvido_pelo_id_independentemente_da_ordem_de_entrada(ordem):
    propostas = [proposta(id_, datetime(2026, 11, 1)) for id_ in ordem]

    _classificar(propostas)

    assert {p.submissao_id.int: p.classificacao for p in propostas} == {1: 1, 2: 2, 3: 3}


def test_empate_sem_data_de_envio_fica_depois_de_proposta_com_data():
    sem_data = proposta(1)
    com_data = proposta(2, datetime(2026, 11, 1))

    _classificar([sem_data, com_data])

    assert com_data.classificacao == 1
    assert sem_data.classificacao == 2


def test_nota_zero_entra_na_classificacao_e_proposta_sem_nota_permanece_sem_posicao():
    zero = proposta(2, notas=("0",), aprovacoes=0)
    sem_nota = proposta(1, notas=(), aprovacoes=0)

    _classificar([sem_nota, zero])

    assert zero.classificacao == 1
    assert sem_nota.classificacao is None


def test_media_nao_depende_do_arredondamento_global_nem_altera_contexto_do_chamador():
    with localcontext() as contexto:
        contexto.prec = 4
        contexto.rounding = ROUND_DOWN

        media = media_das_notas([Decimal("8"), Decimal("7.35")])

        assert media == Decimal("7.68")
        assert contexto.prec == 4
        assert contexto.rounding == ROUND_DOWN
