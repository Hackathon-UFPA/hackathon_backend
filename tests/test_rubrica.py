"""BE-S4-06: critérios, pesos e escalas da rubrica, publicação e imutabilidade
(RF16, RF17, RN09, RN10)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.const.rubrica import CRITERIOS_MINIMOS_RN10
from app.validations.rubrica import (
    criterios_minimos_faltantes,
    normalizar_nome,
    pendencias_para_publicar,
    pode_publicar_no_prazo,
)
from tests.conftest import executar_sql
from tests.test_convites import Cenario, com_token


def criterio(nome, peso, escala_min=0, escala_max=10, descricao="Como o critério é julgado"):
    return {
        "nome": nome,
        "descricao": descricao,
        "peso": str(peso),
        "escala_min": escala_min,
        "escala_max": escala_max,
    }


def criterios_completos():
    """Os critérios mínimos da RN10 com pesos que somam 100."""
    n = len(CRITERIOS_MINIMOS_RN10)
    pesos = [Decimal(100 // n)] * n
    pesos[-1] += Decimal(100) - sum(pesos)
    return [criterio(nome, peso) for nome, peso in zip(CRITERIOS_MINIMOS_RN10, pesos, strict=True)]


class CenarioRubrica(Cenario):
    def __init__(self, *args):
        super().__init__(*args)
        self.organizador = self.usuario_no_banco(papel="ORGANIZADOR")
        self.participante = self.lider

    @property
    def url(self):
        return f"/hackathons/{self.hackathon_id}/rubrica"

    def salvar(self, client, criterios, quem=None, hackathon_id=None):
        url = f"/hackathons/{hackathon_id}/rubrica" if hackathon_id else self.url
        return client.put(
            url,
            json={"criterios": criterios},
            headers=com_token((quem or self.organizador)["id"]),
        )

    def publicar(self, client, quem=None):
        return client.post(
            f"{self.url}/publicar", headers=com_token((quem or self.organizador)["id"])
        )

    def rascunho(self, client, quem=None):
        return client.get(
            f"{self.url}/rascunho", headers=com_token((quem or self.organizador)["id"])
        )

    def inscricoes_inicio(self, dias: int | None):
        valor = None if dias is None else datetime.now(UTC) + timedelta(days=dias)
        self.sql(
            "UPDATE hackathon SET inscricoes_inicio = :v WHERE id = :h",
            v=valor.replace(tzinfo=None) if valor else None,
            h=self.hackathon_id,
        )

    def publicada(self, client):
        assert self.salvar(client, criterios_completos()).status_code == 200
        resposta = self.publicar(client)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def limpar(self):
        for h in self.hackathons:
            self.sql("DELETE FROM rubricas WHERE hackathon_id = :h", h=h)
        super().limpar()


@pytest.fixture
def rubrica(sql, usuario_no_banco, novo_email):
    cenario = CenarioRubrica(sql, usuario_no_banco, novo_email)
    try:
        yield cenario
    finally:
        cenario.limpar()


# --- Regras puras ---


def test_normalizar_nome_ignora_acentos_maiusculas_e_espacos():
    assert normalizar_nome("  Viabilidade   TÉCNICA ") == "viabilidade tecnica"


def test_criterios_minimos_faltantes():
    assert criterios_minimos_faltantes(["inovacao", "Outro"], ["Inovação", "Impacto"]) == [
        "Impacto"
    ]


def test_pendencias_para_publicar():
    assert pendencias_para_publicar([], [], minimos=[]) == [
        "A rubrica precisa de pelo menos um critério.",
        "A soma dos pesos deve ser 100%; está em 0%.",
    ]
    assert pendencias_para_publicar(["A", "B"], [Decimal("50.5"), Decimal("49.5")], []) == []
    assert "99.99" in pendencias_para_publicar(["A"], [Decimal("99.99")], [])[0]


def test_prazo_de_publicacao():
    agora = datetime(2026, 11, 3, 12, tzinfo=UTC)
    assert pode_publicar_no_prazo(None, agora)
    assert pode_publicar_no_prazo(datetime(2026, 11, 4), agora)
    assert not pode_publicar_no_prazo(datetime(2026, 11, 3, 12), agora)
    assert not pode_publicar_no_prazo(datetime(2026, 11, 2), agora)


# --- Edição do rascunho (RF16) ---


def test_organizador_salva_rascunho_incompleto_com_pendencias(client, rubrica):
    resposta = rubrica.salvar(client, [criterio("Inovação", 30, 1, 5)])

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["publicada"] is False
    assert corpo["publicada_em"] is None
    assert Decimal(corpo["soma_pesos"]) == 30
    assert [c["nome"] for c in corpo["criterios"]] == ["Inovação"]
    assert corpo["criterios"][0]["escala_min"] == 1
    assert corpo["criterios"][0]["escala_max"] == 5
    assert any("soma dos pesos" in p for p in corpo["pendencias"])
    assert any("RN10" in p for p in corpo["pendencias"])
    assert rubrica.rascunho(client).json() == corpo


def test_salvar_substitui_a_lista_e_mantem_a_ordem(client, rubrica):
    rubrica.salvar(client, [criterio("Antigo", 10)])
    completos = criterios_completos()[::-1]

    corpo = rubrica.salvar(client, completos).json()

    assert [c["nome"] for c in corpo["criterios"]] == [c["nome"] for c in completos]
    assert [c["ordem"] for c in corpo["criterios"]] == list(range(1, len(completos) + 1))
    assert corpo["pendencias"] == []
    linhas = rubrica.sql(
        "SELECT count(*) AS n FROM rubricas WHERE hackathon_id = :h", h=rubrica.hackathon_id
    )
    assert linhas[0]["n"] == 1


@pytest.mark.parametrize(
    "item",
    [
        criterio("", 10),
        criterio("Sem descrição", 10, descricao=" "),
        criterio("Peso zero", 0),
        criterio("Peso negativo", -5),
        criterio("Peso acima", 100.5),
        criterio("Três casas", "10.123"),
        criterio("Escala invertida", 10, 10, 5),
        criterio("Escala igual", 10, 5, 5),
        criterio("Escala negativa", 10, -1, 5),
    ],
    ids=lambda item: item["nome"] or "nome-vazio",
)
def test_criterio_invalido(client, rubrica, item):
    assert rubrica.salvar(client, [item]).status_code == 422


def test_nomes_repetidos_na_rubrica(client, rubrica):
    resposta = rubrica.salvar(client, [criterio("Inovação", 50), criterio(" inovacao ", 50)])
    assert resposta.status_code == 422


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "COMITE_TECNICO", "COMITE_CIENTIFICO"])
def test_outros_perfis_nao_editam_rubrica(client, rubrica, papel):
    quem = rubrica.usuario_no_banco(papel=papel)
    assert rubrica.salvar(client, criterios_completos(), quem=quem).status_code == 403
    assert rubrica.publicar(client, quem=quem).status_code == 403
    assert rubrica.rascunho(client, quem=quem).status_code == 403


def test_dev_edita_e_publica(client, rubrica):
    dev = rubrica.usuario_no_banco(papel="DEV")
    assert rubrica.salvar(client, criterios_completos(), quem=dev).status_code == 200
    assert rubrica.publicar(client, quem=dev).status_code == 200


def test_rubrica_de_hackathon_inexistente(client, rubrica):
    assert rubrica.salvar(client, [], hackathon_id=uuid4()).status_code == 404
    assert client.get(f"/hackathons/{uuid4()}/rubrica").status_code == 404


def test_rascunho_inexistente(client, rubrica):
    assert rubrica.rascunho(client).status_code == 404
    assert rubrica.publicar(client).status_code == 404


# --- Publicação (RF16, RF17, RN09, RN10) ---


def test_publica_e_consulta_sem_login(client, rubrica):
    publicada = rubrica.publicada(client)

    assert publicada["publicada"] is True
    assert publicada["publicada_em"] is not None
    assert Decimal(publicada["soma_pesos"]) == 100
    resposta = client.get(rubrica.url)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["criterios"] == publicada["criterios"]
    assert {"nome", "descricao", "peso", "escala_min", "escala_max"} <= set(corpo["criterios"][0])
    assert "pendencias" not in corpo


def test_rubrica_nao_publicada_nao_aparece_para_o_publico(client, rubrica):
    rubrica.salvar(client, criterios_completos())
    assert client.get(rubrica.url).status_code == 404


@pytest.mark.parametrize("pesos", [[25, 25, 25, 24], [25, 25, 25, 25.01]])
def test_publicar_exige_soma_100(client, rubrica, pesos):
    itens = [
        criterio(nome, peso) for nome, peso in zip(CRITERIOS_MINIMOS_RN10, pesos, strict=False)
    ]
    rubrica.salvar(client, itens)

    resposta = rubrica.publicar(client)

    assert resposta.status_code == 422
    assert "soma dos pesos" in resposta.json()["detail"]


def test_publicar_exige_criterios_minimos_da_rn10(client, rubrica):
    rubrica.salvar(client, [criterio("Qualquer", 100)])

    resposta = rubrica.publicar(client)

    assert resposta.status_code == 422
    for nome in CRITERIOS_MINIMOS_RN10:
        assert nome in resposta.json()["detail"]


def test_criterios_minimos_aceitam_variacao_de_escrita(client, rubrica):
    itens = criterios_completos()
    for item in itens:
        item["nome"] = item["nome"].upper()
    rubrica.salvar(client, itens)
    assert rubrica.publicar(client).status_code == 200


def test_publicar_sem_criterios(client, rubrica):
    rubrica.salvar(client, [])
    assert rubrica.publicar(client).status_code == 422


@pytest.mark.parametrize(("dias", "status"), [(1, 200), (None, 200), (0, 409), (-1, 409)], ids=str)
def test_publicar_antes_das_inscricoes(client, rubrica, dias, status):
    rubrica.salvar(client, criterios_completos())
    rubrica.inscricoes_inicio(dias)
    assert rubrica.publicar(client).status_code == status


def test_rubrica_publicada_nao_muda(client, rubrica):
    publicada = rubrica.publicada(client)

    assert rubrica.salvar(client, [criterio("Novo", 100)]).status_code == 409
    assert rubrica.publicar(client).status_code == 409
    assert client.get(rubrica.url).json()["criterios"] == publicada["criterios"]
    rascunho = rubrica.rascunho(client).json()
    assert rascunho["publicada"] is True
    assert rascunho["pendencias"] == []


def test_publicacoes_simultaneas_geram_um_sucesso(client, rubrica):
    rubrica.salvar(client, criterios_completos())
    barreira = Barrier(2)

    def publicar():
        barreira.wait(timeout=10)
        return rubrica.publicar(client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        respostas = list(pool.map(lambda _: publicar(), range(2)))

    assert sorted(r.status_code for r in respostas) == [200, 409]


# --- RN09 garantida no banco ---


@pytest.mark.parametrize(
    "comando",
    [
        "UPDATE criterios_rubrica SET peso = 1 WHERE rubrica_id = :r",
        "DELETE FROM criterios_rubrica WHERE rubrica_id = :r",
        "INSERT INTO criterios_rubrica (rubrica_id, nome, descricao, peso, escala_min,"
        " escala_max, ordem) VALUES (:r, 'Extra', 'D', 1, 0, 10, 99)",
        "UPDATE rubricas SET publicada_em = NULL WHERE id = :r",
    ],
    ids=["altera-criterio", "remove-criterio", "inclui-criterio", "despublica"],
)
def test_banco_impede_alterar_rubrica_publicada(client, rubrica, comando):
    publicada = rubrica.publicada(client)

    with pytest.raises(IntegrityError, match="rubrica_publicada_imutavel"):
        executar_sql(comando, r=publicada["id"])


def test_banco_permite_remover_a_rubrica_inteira(client, rubrica):
    publicada = rubrica.publicada(client)

    executar_sql("DELETE FROM rubricas WHERE id = :r", r=publicada["id"])

    assert (
        executar_sql("SELECT 1 FROM criterios_rubrica WHERE rubrica_id = :r", r=publicada["id"])
        == []
    )
