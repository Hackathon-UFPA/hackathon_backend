"""Política de categoria e coerência dos tipos de integrante (BE-S5-01). Não usa banco."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.const.enums import CategoriaEquipe, TipoIntegrante
from app.models import Hackathon
from app.schemas.equipe import ComposicaoUpdate, EquipeCreate, IntegranteIndicado
from app.schemas.hackathon import HackathonCreate, HackathonUpdate
from app.services.composicao import validar_composicao
from app.validations.categoria_equipe import (
    categoria_permitida,
    categorias_permitidas,
    incoerencia_da_composicao,
    resolver_tipo,
    tipo_compativel,
    tipo_padrao,
)

E, P = TipoIntegrante.ESTUDANTE, TipoIntegrante.PROFISSIONAL
ESTUDANTES, PROFISSIONAIS, MISTA = (
    CategoriaEquipe.ESTUDANTES,
    CategoriaEquipe.PROFISSIONAIS,
    CategoriaEquipe.MISTA,
)


def hackathon(**campos) -> Hackathon:
    return Hackathon(min_integrantes=3, max_integrantes=5, **campos)


def indicados(*pares) -> list[IntegranteIndicado]:
    return [
        IntegranteIndicado(nome=f"Pessoa {i}", email=f"p{i}@teste.com", tipo_integrante=tipo)
        for i, tipo in enumerate(pares)
    ]


def mensagem(excecao: pytest.ExceptionInfo[HTTPException]) -> str:
    return excecao.value.detail


@pytest.mark.parametrize(
    "categoria,tipos,coerente",
    [
        (ESTUDANTES, [E, E, E], True),
        (ESTUDANTES, [E, E, P], False),
        (PROFISSIONAIS, [P, P, P], True),
        (PROFISSIONAIS, [P, E, P], False),
        (MISTA, [E, P, P], True),
        (MISTA, [P, E], True),
        (MISTA, [E, E, E], False),
        (MISTA, [P, P, P], False),
    ],
)
def test_coerencia_entre_categoria_e_tipos(categoria, tipos, coerente):
    assert (incoerencia_da_composicao(categoria, tipos) is None) is coerente


def test_tipo_padrao_e_compatibilidade():
    assert tipo_padrao(ESTUDANTES) == E
    assert tipo_padrao(PROFISSIONAIS) == P
    assert tipo_padrao(MISTA) is None
    assert tipo_compativel(ESTUDANTES, E) and not tipo_compativel(ESTUDANTES, P)
    assert tipo_compativel(PROFISSIONAIS, P) and not tipo_compativel(PROFISSIONAIS, E)
    assert tipo_compativel(MISTA, E) and tipo_compativel(MISTA, P)


def test_resolver_tipo():
    assert resolver_tipo(ESTUDANTES, None, "Ana") == E
    assert resolver_tipo(PROFISSIONAIS, None, "Ana") == P
    assert resolver_tipo(MISTA, P, "Ana") == P
    with pytest.raises(HTTPException) as obrigatorio:
        resolver_tipo(MISTA, None, "Ana")
    assert obrigatorio.value.status_code == 422
    with pytest.raises(HTTPException) as incompativel:
        resolver_tipo(ESTUDANTES, P, "Ana")
    assert incompativel.value.status_code == 422


def test_politica_padrao_libera_as_tres_categorias_e_pode_restringir():
    assert categorias_permitidas(
        hackathon(
            aceita_equipe_estudantes=True,
            aceita_equipe_profissionais=True,
            aceita_equipe_mista=True,
        )
    ) == [ESTUDANTES, PROFISSIONAIS, MISTA]
    so_estudantes = hackathon(
        aceita_equipe_estudantes=True, aceita_equipe_profissionais=False, aceita_equipe_mista=False
    )
    assert categoria_permitida(so_estudantes, ESTUDANTES)
    assert not categoria_permitida(so_estudantes, MISTA)


def test_composicao_valida_devolve_tipos_normalizados():
    tipo_lider, lista = validar_composicao(
        hackathon(),
        MISTA,
        tipo_lider=E,
        email_lider="lider@teste.com",
        integrantes=[
            IntegranteIndicado(nome="Ana", email="ANA@Teste.com", tipo_integrante=P),
            IntegranteIndicado(nome="Bia", email="bia@teste.com", tipo_integrante=E),
        ],
    )
    assert tipo_lider == E
    assert [(i.email, i.tipo) for i in lista] == [("ana@teste.com", P), ("bia@teste.com", E)]


@pytest.mark.parametrize(
    "categoria,tipo_lider,tipos,trecho",
    [
        (ESTUDANTES, None, [None], "de 3 a 5"),  # total 2
        (ESTUDANTES, None, [None] * 5, "de 3 a 5"),  # total 6
        (MISTA, E, [E, E], "ao menos um ESTUDANTE e um PROFISSIONAL"),
        (MISTA, None, [E, P], "tipo"),  # líder sem tipo na MISTA
        (MISTA, E, [None, P], "tipo"),  # integrante sem tipo na MISTA
        (ESTUDANTES, None, [P, None], "não cabe"),
        (PROFISSIONAIS, E, [None, None], "não cabe"),
    ],
)
def test_composicao_invalida_da_422(categoria, tipo_lider, tipos, trecho):
    with pytest.raises(HTTPException) as erro:
        validar_composicao(
            hackathon(),
            categoria,
            tipo_lider=tipo_lider,
            email_lider="lider@teste.com",
            integrantes=indicados(*tipos),
        )
    assert erro.value.status_code == 422
    assert trecho in mensagem(erro)


def test_email_repetido_e_lider_na_lista_dao_422():
    repetidos = [
        IntegranteIndicado(nome="Ana", email="ana@teste.com"),
        IntegranteIndicado(nome="Ana 2", email="ANA@teste.com"),
    ]
    with pytest.raises(HTTPException) as erro:
        validar_composicao(
            hackathon(), ESTUDANTES, tipo_lider=None, email_lider="x@t.com", integrantes=repetidos
        )
    assert erro.value.status_code == 422 and "repetido" in mensagem(erro)

    com_lider = [
        IntegranteIndicado(nome="Eu", email="LIDER@teste.com"),
        IntegranteIndicado(nome="B", email="b@teste.com"),
    ]
    with pytest.raises(HTTPException) as erro:
        validar_composicao(
            hackathon(),
            ESTUDANTES,
            tipo_lider=None,
            email_lider="lider@teste.com",
            integrantes=com_lider,
        )
    assert erro.value.status_code == 422 and "líder" in mensagem(erro)


def test_categoria_que_a_edicao_nao_aceita_da_422_com_as_aceitas():
    so_estudantes = hackathon(
        aceita_equipe_estudantes=True, aceita_equipe_profissionais=False, aceita_equipe_mista=False
    )
    with pytest.raises(HTTPException) as erro:
        validar_composicao(
            so_estudantes,
            MISTA,
            tipo_lider=E,
            email_lider="l@t.com",
            integrantes=indicados(P, E),
        )
    assert erro.value.status_code == 422 and "ESTUDANTES" in mensagem(erro)


def test_limites_seguem_a_configuracao_da_edicao():
    pequena = Hackathon(
        min_integrantes=2,
        max_integrantes=2,
        aceita_equipe_estudantes=True,
        aceita_equipe_profissionais=True,
        aceita_equipe_mista=True,
    )
    _, lista = validar_composicao(
        pequena, ESTUDANTES, tipo_lider=None, email_lider="l@t.com", integrantes=indicados(None)
    )
    assert len(lista) == 1


@pytest.mark.parametrize(
    "campo", ["termos_ids", "aceitou_termos", "comprovante", "arquivo_url", "usuario_id", "senha"]
)
def test_lider_nao_envia_termos_nem_comprovante_de_terceiros(campo):
    """RN05 e RN25: o schema do que o líder indica não aceita nada além de nome, e-mail e tipo."""
    with pytest.raises(ValidationError):
        IntegranteIndicado.model_validate({"nome": "Ana", "email": "a@t.com", campo: "x"})
    with pytest.raises(ValidationError):
        EquipeCreate.model_validate(
            {"hackathon_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", campo: "x"}
        )
    with pytest.raises(ValidationError):
        ComposicaoUpdate.model_validate({"categoria": "MISTA", "integrantes": [], campo: "x"})


def test_teto_de_integrantes_por_pedido():
    itens = [{"nome": f"P{i}", "email": f"p{i}@t.com"} for i in range(21)]
    with pytest.raises(ValidationError):
        ComposicaoUpdate.model_validate({"categoria": "ESTUDANTES", "integrantes": itens})


def test_hackathon_precisa_aceitar_ao_menos_uma_categoria():
    with pytest.raises(ValidationError):
        HackathonCreate(
            aceita_equipe_estudantes=False,
            aceita_equipe_profissionais=False,
            aceita_equipe_mista=False,
        )
    with pytest.raises(ValidationError):
        HackathonUpdate.model_validate({"aceita_equipe_mista": None})
    assert HackathonCreate().aceita_equipe_mista is True
