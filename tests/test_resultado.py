"""BE-S4-11: homologação do resultado (RF31) e divulgação das propostas aprovadas (RF32)."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from app.services.resultado import media_das_notas
from tests.test_avaliacao_designacoes import CenarioAvaliacao
from tests.test_convites import com_token


class CenarioResultado(CenarioAvaliacao):
    """Três propostas ENVIADA, dois avaliadores e N = 2, todas já designadas aos dois."""

    def __init__(self, sql, usuario_no_banco):
        super().__init__(sql, usuario_no_banco)
        self.propostas = self.pronto(3, 2, 2)
        for proposta in self.propostas:
            for avaliador in self.avaliadores:
                self.designar(proposta, avaliador)

    @property
    def base(self):
        return f"/admin/hackathons/{self.hackathon_id}/resultado"

    def avaliar(self, proposta, avaliador, nota, recomendacao="APROVACAO", status="ENVIADA"):
        self.sql(
            "INSERT INTO avaliacoes (submissao_id, avaliador_id, nota, avaliado_em, status,"
            " recomendacao) VALUES (:s, :a, :n, now(), CAST(:st AS status_avaliacao),"
            " CAST(:r AS recomendacao_avaliacao))",
            s=proposta,
            a=avaliador["id"],
            n=None if status == "RASCUNHO" else nota,
            st=status,
            r=recomendacao,
        )

    def avaliar_tudo(self):
        """Médias: proposta 0 = 9,00; proposta 1 = 7,68 (8 e 7,35); proposta 2 = 5,00."""
        notas = [("9", "9"), ("8", "7.35"), ("6", "4")]
        for proposta, par in zip(self.propostas, notas, strict=True):
            for avaliador, nota in zip(self.avaliadores, par, strict=True):
                recomendacao = "APROVACAO" if Decimal(nota) >= 7 else "REPROVACAO"
                self.avaliar(proposta, avaliador, nota, recomendacao)

    def nomear(self, proposta, equipe):
        self.sql(
            "UPDATE equipes SET nome = :n WHERE id = (SELECT equipe_id FROM submissoes"
            " WHERE id = :s)",
            n=equipe,
            s=proposta,
        )

    def consultar(self, client, quem=None):
        return client.get(self.base, headers=com_token((quem or self.organizador)["id"]))

    def homologar(self, client, aprovadas, quem=None):
        return client.post(
            f"{self.base}/homologar",
            json={"propostas_aprovadas": [str(a) for a in aprovadas]},
            headers=com_token((quem or self.organizador)["id"]),
        )

    def publico(self, client, hackathon_id=None):
        return client.get(f"/hackathons/{hackathon_id or self.hackathon_id}/propostas-aprovadas")

    def homologacoes(self):
        return self.sql(
            "SELECT * FROM homologacoes_resultado WHERE hackathon_id = :h", h=self.hackathon_id
        )

    def limpar(self):
        # resultados_proposta sai em cascata com a homologação
        self.sql("DELETE FROM homologacoes_resultado WHERE hackathon_id = :h", h=self.hackathon_id)
        super().limpar()


@pytest.fixture
def resultado(sql, usuario_no_banco):
    cenario = CenarioResultado(sql, usuario_no_banco)
    try:
        yield cenario
    finally:
        cenario.limpar()


def _codigos(resposta):
    return [p["codigo"] for p in resposta.json()["pendencias"]]


def test_media_arredonda_so_no_fim_com_half_up():
    assert media_das_notas([]) is None
    assert media_das_notas([Decimal("8"), Decimal("7.35")]) == Decimal("7.68")
    assert media_das_notas([Decimal("7.01"), Decimal("7.02"), Decimal("7.02")]) == Decimal("7.02")


def test_consolida_notas_e_classifica(client, resultado):
    resultado.avaliar_tudo()
    resposta = resultado.consultar(client)
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["homologado"] is False
    assert corpo["pode_homologar"] is True
    assert corpo["pendencias"] == []
    assert corpo["total_propostas"] == 3
    assert corpo["total_aprovadas"] is None
    linhas = corpo["propostas"]
    assert [linha["submissao_id"] for linha in linhas] == [str(p) for p in resultado.propostas]
    assert [linha["nota_media"] for linha in linhas] == ["9.00", "7.68", "5.00"]
    assert [linha["classificacao"] for linha in linhas] == [1, 2, 3]
    assert [linha["aprovada"] for linha in linhas] == [None, None, None]
    assert linhas[1]["recomendacoes_aprovacao"] == 2
    assert linhas[2]["recomendacoes_reprovacao"] == 2
    assert linhas[0]["avaliadores_designados"] == linhas[0]["avaliacoes_enviadas"] == 2


def test_empate_na_media_desempata_por_recomendacoes_de_aprovacao(client, resultado):
    primeira, segunda, terceira = resultado.propostas
    a, b = resultado.avaliadores
    # Mesma média 7,00: a segunda tem duas recomendações de aprovação, a primeira só uma
    resultado.avaliar(primeira, a, "7", "APROVACAO")
    resultado.avaliar(primeira, b, "7", "REPROVACAO")
    resultado.avaliar(segunda, a, "7", "APROVACAO")
    resultado.avaliar(segunda, b, "7", "APROVACAO")
    resultado.avaliar(terceira, a, "3", "REPROVACAO")
    resultado.avaliar(terceira, b, "3", "REPROVACAO")
    linhas = resultado.consultar(client).json()["propostas"]
    assert [linha["submissao_id"] for linha in linhas[:2]] == [str(segunda), str(primeira)]


def test_avaliacao_faltando_ou_em_rascunho_impede_homologar(client, resultado):
    resultado.avaliar_tudo()
    resultado.sql(
        "DELETE FROM avaliacoes WHERE submissao_id = :s AND avaliador_id = :a",
        s=resultado.propostas[0],
        a=resultado.avaliadores[0]["id"],
    )
    resultado.avaliar(resultado.propostas[0], resultado.avaliadores[0], None, None, "RASCUNHO")
    resultado.sql("DELETE FROM avaliacoes WHERE submissao_id = :s", s=resultado.propostas[1])
    resposta = resultado.consultar(client)
    corpo = resposta.json()
    assert corpo["pode_homologar"] is False
    assert _codigos(resposta) == ["AVALIACAO_PENDENTE", "AVALIACAO_PENDENTE"]
    sem_nota = next(
        p for p in corpo["propostas"] if p["submissao_id"] == str(resultado.propostas[1])
    )
    assert sem_nota["nota_media"] is None and sem_nota["classificacao"] is None
    # O rascunho não entra na média
    com_rascunho = next(
        p for p in corpo["propostas"] if p["submissao_id"] == str(resultado.propostas[0])
    )
    assert com_rascunho["avaliacoes_enviadas"] == 1
    assert com_rascunho["nota_media"] == "9.00"

    homologacao = resultado.homologar(client, [])
    assert homologacao.status_code == 409
    assert resultado.homologacoes() == []


def test_avaliadores_insuficientes_e_quantidade_nao_configurada(client, resultado):
    resultado.avaliar_tudo()
    resultado.configurar(3)
    assert _codigos(resultado.consultar(client)) == ["AVALIADORES_INSUFICIENTES"] * 3
    resultado.configurar(None)
    assert _codigos(resultado.consultar(client)) == ["QUANTIDADE_NAO_CONFIGURADA"]
    assert resultado.homologar(client, []).status_code == 409


def test_sem_propostas_nao_homologa(client, resultado):
    resultado.sql(
        "DELETE FROM designacoes_avaliacao WHERE hackathon_id = :h", h=resultado.hackathon_id
    )
    resultado.sql(
        "UPDATE submissoes SET status = 'RASCUNHO' WHERE hackathon_id = :h",
        h=resultado.hackathon_id,
    )
    resposta = resultado.consultar(client)
    assert _codigos(resposta) == ["SEM_PROPOSTAS"]
    assert resposta.json()["propostas"] == []
    assert resultado.homologar(client, []).status_code == 409


def test_homologa_grava_auditoria_e_bloqueia_resultado(client, resultado):
    resultado.avaliar_tudo()
    primeira, segunda, terceira = resultado.propostas
    resposta = resultado.homologar(client, [primeira, segunda])
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["homologado"] is True
    assert corpo["pode_homologar"] is False
    assert corpo["homologado_por"] == str(resultado.organizador["id"])
    assert corpo["homologado_em"] is not None
    assert corpo["total_propostas"] == 3
    assert corpo["total_aprovadas"] == 2
    assert [p["aprovada"] for p in corpo["propostas"]] == [True, True, False]
    assert [p["classificacao"] for p in corpo["propostas"]] == [1, 2, 3]

    (registro,) = resultado.homologacoes()
    assert registro["homologado_por"] == resultado.organizador["id"]
    assert resultado.consultar(client).json() == corpo

    # Bloqueado: homologar de novo não muda nada
    segunda_vez = resultado.homologar(client, [terceira])
    assert segunda_vez.status_code == 409
    assert resultado.consultar(client).json() == corpo


def test_depois_de_homologado_avaliacao_e_distribuicao_ficam_bloqueadas(client, resultado):
    resultado.avaliar_tudo()
    assert resultado.homologar(client, [resultado.propostas[0]]).status_code == 200
    proposta = resultado.propostas[0]
    avaliador = resultado.avaliadores[0]

    rascunho = client.put(
        f"/avaliador/propostas/{proposta}/avaliacao/rascunho",
        json={},
        headers=com_token(avaliador["id"]),
    )
    assert rascunho.status_code == 409
    assert "homologado" in rascunho.json()["detail"]
    assert resultado.distribuir(client).status_code == 409
    assert resultado.redistribuir(client, proposta, resultado.avaliadores).status_code == 409
    configuracao = client.patch(
        f"/admin/hackathons/{resultado.hackathon_id}/avaliacao/configuracao",
        json={"avaliadores_por_proposta": 3},
        headers=com_token(resultado.organizador["id"]),
    )
    assert configuracao.status_code == 409
    assert (
        resultado.sql(
            "SELECT avaliadores_por_proposta FROM hackathon WHERE id = :h", h=resultado.hackathon_id
        )[0]["avaliadores_por_proposta"]
        == 2
    )


def test_banco_impede_alterar_resultado_homologado(client, resultado):
    resultado.avaliar_tudo()
    assert resultado.homologar(client, []).status_code == 200
    with pytest.raises(DBAPIError, match="resultado_homologado_imutavel"):
        resultado.sql(
            "UPDATE resultados_proposta SET aprovada = true WHERE hackathon_id = :h",
            h=resultado.hackathon_id,
        )
    with pytest.raises(DBAPIError, match="resultado_homologado_imutavel"):
        resultado.sql(
            "UPDATE homologacoes_resultado SET total_aprovadas = 1 WHERE hackathon_id = :h",
            h=resultado.hackathon_id,
        )


@pytest.mark.parametrize("defeito", ["repetida", "inexistente", "rascunho", "outro-hackathon"])
def test_lista_de_aprovadas_invalida_responde_422(client, resultado, defeito):
    resultado.avaliar_tudo()
    primeira = resultado.propostas[0]
    outra = None
    if defeito == "repetida":
        aprovadas = [primeira, primeira]
    elif defeito == "inexistente":
        aprovadas = [uuid4()]
    elif defeito == "rascunho":
        aprovadas = [resultado.proposta("RASCUNHO")]
    else:
        outra = CenarioAvaliacao(resultado.sql, resultado.usuario_no_banco)
        aprovadas = [outra.proposta()]
    try:
        assert resultado.homologar(client, aprovadas).status_code == 422
        assert resultado.homologacoes() == []
    finally:
        if outra is not None:
            outra.limpar()


def test_corpo_com_campo_extra_responde_422(client, resultado):
    resultado.avaliar_tudo()
    resposta = client.post(
        f"{resultado.base}/homologar",
        json={"propostas_aprovadas": [], "homologado_por": str(uuid4())},
        headers=com_token(resultado.organizador["id"]),
    )
    assert resposta.status_code == 422


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO", "COMITE_CIENTIFICO"])
def test_so_organizador_consulta_e_homologa(client, resultado, papel):
    resultado.avaliar_tudo()
    usuario = resultado.usuario_no_banco(papel=papel, senha=None)
    assert resultado.consultar(client, quem=usuario).status_code == 403
    assert resultado.homologar(client, [], quem=usuario).status_code == 403
    assert resultado.homologacoes() == []


def test_sem_token_responde_401_e_dev_pode_homologar(client, resultado):
    resultado.avaliar_tudo()
    assert client.get(resultado.base).status_code == 401
    assert (
        client.post(f"{resultado.base}/homologar", json={"propostas_aprovadas": []}).status_code
        == 401
    )
    dev = resultado.usuario_no_banco(papel="DEV", senha=None)
    assert resultado.homologar(client, [], quem=dev).status_code == 200


def test_hackathon_inexistente_responde_404(client, resultado):
    outro = uuid4()
    headers = com_token(resultado.organizador["id"])
    assert client.get(f"/admin/hackathons/{outro}/resultado", headers=headers).status_code == 404
    assert (
        client.post(
            f"/admin/hackathons/{outro}/resultado/homologar",
            json={"propostas_aprovadas": []},
            headers=headers,
        ).status_code
        == 404
    )
    assert resultado.publico(client, outro).status_code == 404


def test_lista_publica_so_aparece_depois_da_homologacao(client, resultado):
    resultado.avaliar_tudo()
    antes = resultado.publico(client)
    assert antes.status_code == 200
    assert antes.json() == {
        "hackathon_id": str(resultado.hackathon_id),
        "hackathon_nome": "Teste de designações",
        "divulgado": False,
        "divulgado_em": None,
        "propostas": [],
    }


def test_lista_publica_mostra_equipe_tema_e_titulo_sem_login(client, resultado):
    resultado.avaliar_tudo()
    primeira, segunda, terceira = resultado.propostas
    resultado.nomear(primeira, "Zeta")
    resultado.nomear(segunda, "Alfa")
    resultado.nomear(terceira, "Beta")
    assert resultado.homologar(client, [primeira, segunda]).status_code == 200

    resposta = resultado.publico(client)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["divulgado"] is True
    assert corpo["divulgado_em"] is not None
    # Só aprovadas, em ordem alfabética pela equipe, sem notas
    assert corpo["propostas"] == [
        {"submissao_id": str(segunda), "equipe": "Alfa", "tema": "Tema", "titulo": "Enviada"},
        {"submissao_id": str(primeira), "equipe": "Zeta", "tema": "Tema", "titulo": "Enviada"},
    ]

    # O resultado é um retrato: renomear a equipe depois não muda o que foi divulgado
    resultado.nomear(segunda, "Outro nome")
    assert resultado.publico(client).json() == corpo
