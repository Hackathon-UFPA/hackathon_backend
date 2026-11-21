from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models import Hackathon, Submissao
from app.validations.submissao import campos_obrigatorios_pendentes, propostas_abertas


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


@pytest.mark.parametrize("campo", ["titulo", "descricao", "bases_dados"])
def test_espacos_unicode_nao_preenchem_texto_obrigatorio(proposta, campo):
    setattr(proposta, campo, "\u00a0\u2003")

    assert campos_obrigatorios_pendentes(proposta) == [campo]


@pytest.mark.parametrize(
    "ods",
    [
        pytest.param([0, 1], id="abaixo-do-minimo"),
        pytest.param([17, 18], id="acima-do-maximo"),
        pytest.param([1, None, 17], id="elemento-nulo"),
    ],
)
def test_ods_validos_na_mesma_lista_nao_compensam_item_invalido(proposta, ods):
    proposta.ods = ods

    assert campos_obrigatorios_pendentes(proposta) == ["ods"]


def test_todas_as_pendencias_sao_informadas_juntas_na_ordem_do_formulario():
    rascunho = Submissao(equipe_id=uuid4(), hackathon_id=uuid4())

    assert campos_obrigatorios_pendentes(rascunho) == [
        "tema_id",
        "titulo",
        "descricao",
        "bases_dados",
        "ods",
    ]


def test_documento_opcional_e_limites_de_ods_nao_bloqueiam_proposta_completa(proposta):
    assert proposta.documento_url is None
    antes = proposta.model_dump()

    assert campos_obrigatorios_pendentes(proposta) == []
    assert proposta.model_dump() == antes


@pytest.mark.parametrize(
    "inicio_inscricoes,fim_inscricoes,inicio_propostas,fim_propostas,permitido",
    [
        pytest.param(-5, -1, -1, 1, True, id="inscricoes-encerradas"),
        pytest.param(-1, 1, 1, 5, False, id="propostas-ainda-fechadas"),
        pytest.param(-1, 1, -5, -1, False, id="propostas-encerradas"),
    ],
)
def test_prazo_de_propostas_independe_das_datas_de_inscricao(
    inicio_inscricoes, fim_inscricoes, inicio_propostas, fim_propostas, permitido
):
    agora = datetime(2026, 11, 15, tzinfo=UTC)
    hackathon = Hackathon(
        inscricoes_inicio=agora + timedelta(days=inicio_inscricoes),
        inscricoes_fim=agora + timedelta(days=fim_inscricoes),
        propostas_inicio=agora + timedelta(days=inicio_propostas),
        propostas_fim=agora + timedelta(days=fim_propostas),
    )

    assert propostas_abertas(hackathon, agora) is permitido
