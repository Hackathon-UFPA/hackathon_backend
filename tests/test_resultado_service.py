from datetime import datetime
from decimal import ROUND_DOWN, Decimal, localcontext
from uuid import UUID

import pytest

from app.services.resultado import _classificar, _Consolidado, media_das_notas

pytestmark = pytest.mark.unit


def proposta(id_, *, enviado_em=None, notas=("8",)):
    return _Consolidado(
        submissao_id=UUID(int=id_),
        equipe_id=UUID(int=100 + id_),
        equipe_nome=None,
        tema_titulo=None,
        titulo=None,
        enviado_em=enviado_em,
        notas=[Decimal(nota) for nota in notas],
        aprovacao=2,
    )


def test_empate_em_media_e_recomendacoes_prioriza_envio_mais_antigo():
    antiga = proposta(2, enviado_em=datetime(2026, 11, 1))
    recente = proposta(1, enviado_em=datetime(2026, 11, 2))

    _classificar([recente, antiga])

    assert (antiga.classificacao, recente.classificacao) == (1, 2)


@pytest.mark.parametrize("ordem", [(3, 1, 2), (2, 3, 1), (1, 2, 3)])
def test_empate_completo_desempata_por_identificador(ordem):
    propostas = [proposta(id_, enviado_em=datetime(2026, 11, 1)) for id_ in ordem]

    _classificar(propostas)

    assert {item.submissao_id.int: item.classificacao for item in propostas} == {1: 1, 2: 2, 3: 3}


def test_empate_sem_data_fica_depois_de_proposta_com_data():
    sem_data = proposta(1)
    com_data = proposta(2, enviado_em=datetime(2026, 11, 1))

    _classificar([sem_data, com_data])

    assert (com_data.classificacao, sem_data.classificacao) == (1, 2)


def test_nota_zero_entra_na_classificacao_e_proposta_sem_nota_fica_sem_posicao():
    zero = proposta(2, notas=("0",))
    sem_nota = proposta(1, notas=())

    _classificar([sem_nota, zero])

    assert zero.classificacao == 1
    assert sem_nota.classificacao is None


def test_media_preserva_arredondamento_e_precisao_do_chamador():
    with localcontext() as contexto:
        contexto.prec = 2
        contexto.rounding = ROUND_DOWN

        assert media_das_notas([Decimal("8"), Decimal("7.35")]) == Decimal("7.68")
        assert contexto.prec == 2
        assert contexto.rounding == ROUND_DOWN
