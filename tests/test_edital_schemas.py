"""Validação direta dos schemas de hackathon, temas e rubrica."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.hackathon import HackathonCreate, HackathonUpdate
from app.schemas.rubrica import CriterioRubricaIn, RubricaUpdate
from app.schemas.tema import TemaCreate, TemaUpdate

pytestmark = pytest.mark.unit


def criterio(**mudancas):
    return {
        "nome": "Inovação",
        "descricao": "Originalidade da solução",
        "peso": "30",
        "escala_min": 0,
        "escala_max": 10,
        **mudancas,
    }


@pytest.mark.parametrize("minimo, maximo", [(1, 1), (3, 5), (5, 5)])
def test_hackathon_aceita_limites_positivos_inclusive_iguais(minimo, maximo):
    dados = HackathonCreate(min_integrantes=minimo, max_integrantes=maximo)

    assert (dados.min_integrantes, dados.max_integrantes) == (minimo, maximo)


@pytest.mark.parametrize("minimo, maximo", [(0, 5), (3, 0), (6, 5)])
def test_hackathon_rejeita_limites_zero_ou_invertidos(minimo, maximo):
    with pytest.raises(ValidationError):
        HackathonCreate(min_integrantes=minimo, max_integrantes=maximo)


@pytest.mark.parametrize("campo", ["status", "min_integrantes", "max_integrantes"])
def test_atualizacao_de_hackathon_rejeita_null_em_campo_obrigatorio(campo):
    with pytest.raises(ValidationError) as erro:
        HackathonUpdate.model_validate({campo: None})

    assert erro.value.errors()[0]["loc"] == (campo,)


@pytest.mark.parametrize("schema", [HackathonUpdate, TemaUpdate])
def test_patch_vazio_preserva_diferenca_entre_campo_omitido_e_null(schema):
    assert schema().model_dump(exclude_unset=True) == {}


def test_tema_normaliza_textos_e_ordena_ods_sem_repeticao():
    dados = TemaCreate(titulo="  Inovação  ", descricao="  Descrição  ", ods=[17, 1, 17])

    assert dados.titulo == "Inovação"
    assert dados.descricao == "Descrição"
    assert dados.ods == [1, 17]


@pytest.mark.parametrize("ods", [[], [0], [18], [1, 18]])
def test_tema_rejeita_ods_vazios_ou_fora_do_intervalo(ods):
    with pytest.raises(ValidationError) as erro:
        TemaCreate(titulo="Tema", descricao="Descrição", ods=ods)

    assert erro.value.errors()[0]["loc"][0] == "ods"


@pytest.mark.parametrize("campo", ["titulo", "descricao", "ods", "ativo"])
def test_atualizacao_de_tema_rejeita_null_em_campo_obrigatorio(campo):
    with pytest.raises(ValidationError) as erro:
        TemaUpdate.model_validate({campo: None})

    assert erro.value.errors()[0]["loc"] == (campo,)


def test_peso_da_rubrica_e_decimal_com_duas_casas():
    dados = CriterioRubricaIn.model_validate(criterio(peso="30.5"))

    assert dados.peso == Decimal("30.50")
    assert dados.peso.as_tuple().exponent == -2


@pytest.mark.parametrize("peso", ["0", "-1", "100.01", "1.001", "NaN", "Infinity"])
def test_peso_rejeita_valores_invalidos_ou_precisao_excessiva(peso):
    with pytest.raises(ValidationError) as erro:
        CriterioRubricaIn.model_validate(criterio(peso=peso))

    assert erro.value.errors()[0]["loc"] == ("peso",)


@pytest.mark.parametrize("minimo, maximo", [(-1, 10), (1, 1), (10, 5), (0, 1001)])
def test_escala_da_rubrica_precisa_ser_crescente_e_respeitar_limites(minimo, maximo):
    with pytest.raises(ValidationError):
        CriterioRubricaIn.model_validate(criterio(escala_min=minimo, escala_max=maximo))


@pytest.mark.parametrize("nome", ["  INOVAÇÃO  ", "inovacao", "INOVACAO"])
def test_rubrica_rejeita_nomes_repetidos_apos_normalizacao(nome):
    with pytest.raises(ValidationError, match="mesmo nome"):
        RubricaUpdate.model_validate({"criterios": [criterio(), criterio(nome=nome)]})


def test_rascunho_de_rubrica_aceita_lista_vazia():
    assert RubricaUpdate(criterios=[]).criterios == []


@pytest.mark.parametrize("quantidade", [50, 51])
def test_rubrica_aceita_no_maximo_50_criterios(quantidade):
    dados = {"criterios": [criterio(nome=f"Critério {i}") for i in range(quantidade)]}

    if quantidade == 50:
        assert len(RubricaUpdate.model_validate(dados).criterios) == 50
    else:
        with pytest.raises(ValidationError) as erro:
            RubricaUpdate.model_validate(dados)
        assert erro.value.errors()[0]["loc"] == ("criterios",)
