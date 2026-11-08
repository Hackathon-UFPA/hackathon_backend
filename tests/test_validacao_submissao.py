"""Completude da proposta sem persistir rascunhos ou chamar a API."""

from uuid import uuid4

import pytest

from app.models import Submissao
from app.validations.submissao import campos_obrigatorios_pendentes


@pytest.fixture
def proposta():
    return Submissao(
        equipe_id=uuid4(),
        hackathon_id=uuid4(),
        tema_id=uuid4(),
        titulo="Monitoramento ambiental",
        descricao="Análise de dados ambientais",
        bases_dados="Dados públicos do INPE",
        ods=[1, 17],
    )


def test_proposta_completa_nao_tem_pendencias(proposta):
    assert campos_obrigatorios_pendentes(proposta) == []


@pytest.mark.parametrize("campo", ["titulo", "descricao", "bases_dados"])
@pytest.mark.parametrize("valor", [None, "", " \t\n "])
def test_texto_obrigatorio_ausente_ou_em_branco_e_pendente(proposta, campo, valor):
    setattr(proposta, campo, valor)

    assert campos_obrigatorios_pendentes(proposta) == [campo]


@pytest.mark.parametrize("ods", [None, [], [0], [18], [1, None], [1, 18]])
def test_ods_precisa_ter_ao_menos_um_item_e_todos_validos(proposta, ods):
    proposta.ods = ods

    assert campos_obrigatorios_pendentes(proposta) == ["ods"]


def test_todas_as_pendencias_sao_informadas_juntas_na_ordem_do_formulario():
    proposta = Submissao(equipe_id=uuid4(), hackathon_id=uuid4())

    assert campos_obrigatorios_pendentes(proposta) == [
        "tema_id",
        "titulo",
        "descricao",
        "bases_dados",
        "ods",
    ]


def test_campos_opcionais_nao_bloqueiam_envio_nem_alteram_a_proposta(proposta):
    antes = proposta.model_dump()

    assert campos_obrigatorios_pendentes(proposta) == []
    assert proposta.model_dump() == antes
