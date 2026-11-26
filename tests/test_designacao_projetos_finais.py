"""BE-S6-09 (RF47, RF48, RN11, RN13, Q07): projetos finais designados ao Comitê Técnico."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from tests.test_convites import com_token


class CenarioTecnico:
    """Hackathon ATIVO com resultado científico homologado e avaliadores do Comitê Técnico.

    O banco de testes é compartilhado: os técnicos elegíveis que já existem são desativados
    durante o teste (e reativados no fim), para que os elegíveis sejam só os criados aqui.
    """

    def __init__(self, sql, usuario_no_banco):
        self.sql = sql
        self.usuario_no_banco = usuario_no_banco
        self.preexistentes = [
            linha["id"]
            for linha in sql(
                "SELECT id FROM usuarios WHERE papel = 'COMITE_TECNICO'"
                " AND ativo AND situacao_conta = 'ATIVA'"
            )
        ]
        if self.preexistentes:
            sql("UPDATE usuarios SET ativo = false WHERE id = ANY(:ids)", ids=self.preexistentes)
        self.hackathon_id = sql(
            "INSERT INTO hackathon (nome, status, data_inicio) VALUES"
            " ('Teste de projetos finais', 'ATIVO', '2097-01-01') RETURNING id"
        )[0]["id"]
        self.tema_id = sql(
            "INSERT INTO temas (hackathon_id, titulo, ativo) VALUES (:h, 'Tema', true)"
            " RETURNING id",
            h=self.hackathon_id,
        )[0]["id"]
        self.organizador = usuario_no_banco(papel="ORGANIZADOR", senha=None)
        self.avaliadores: list[dict] = []
        self.homologacao_id = None
        self.equipe_de: dict = {}
        self.lider_de: dict = {}
        self._classificacao = 0

    def configurar(self, n: int | None):
        self.sql(
            "UPDATE hackathon SET avaliadores_por_projeto_final = :n WHERE id = :h",
            n=n,
            h=self.hackathon_id,
        )

    def definir_status(self, status: str):
        self.sql(
            "UPDATE hackathon SET status = CAST(:s AS status_hackathon) WHERE id = :h",
            s=status,
            h=self.hackathon_id,
        )

    def avaliador(self, **campos) -> dict:
        usuario = self.usuario_no_banco(papel="COMITE_TECNICO", senha=None, **campos)
        self.avaliadores.append(usuario)
        return usuario

    def homologar(self):
        if self.homologacao_id is None:
            self.homologacao_id = self.sql(
                "INSERT INTO homologacoes_resultado (hackathon_id, homologado_por,"
                " total_propostas, total_aprovadas) VALUES (:h, :u, 0, 0) RETURNING id",
                h=self.hackathon_id,
                u=self.organizador["id"],
            )[0]["id"]
        return self.homologacao_id

    def projeto(self, aprovada: bool = True):
        """Proposta ENVIADA com resultado homologado (aprovada ou não)."""
        lider = self.usuario_no_banco(senha=None)
        equipe_id = self.sql(
            "INSERT INTO equipes (hackathon_id, nome) VALUES (:h, 'Equipe') RETURNING id",
            h=self.hackathon_id,
        )[0]["id"]
        self.sql(
            "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id, funcao)"
            " VALUES (:e, :u, :h, 'LIDER')",
            e=equipe_id,
            u=lider["id"],
            h=self.hackathon_id,
        )
        submissao_id = self.sql(
            "INSERT INTO submissoes (equipe_id, hackathon_id, tema_id, status, titulo,"
            " descricao, ods, bases_dados, enviado_em) VALUES (:e, :h, :t, 'ENVIADA',"
            " 'Projeto', 'Descrição', '{1}', 'IBGE', now()) RETURNING id",
            e=equipe_id,
            h=self.hackathon_id,
            t=self.tema_id,
        )[0]["id"]
        self._classificacao += 1
        self.sql(
            "INSERT INTO resultados_proposta (homologacao_id, hackathon_id, submissao_id,"
            " equipe_id, titulo, nota_media, classificacao, avaliacoes, recomendacoes_aprovacao,"
            " recomendacoes_reprovacao, aprovada)"
            " VALUES (:hom, :h, :s, :e, 'Projeto', 8, :c, 2, 2, 0, :ap)",
            hom=self.homologar(),
            h=self.hackathon_id,
            s=submissao_id,
            e=equipe_id,
            c=self._classificacao,
            ap=aprovada,
        )
        self.equipe_de[submissao_id] = equipe_id
        self.lider_de[submissao_id] = lider
        return submissao_id

    def pronto(self, projetos: int, avaliadores: int, n: int):
        self.configurar(n)
        ids = [self.projeto() for _ in range(projetos)]
        for _ in range(avaliadores):
            self.avaliador()
        return ids

    def designacoes(self, projeto_id=None, *, vigentes: bool = True):
        filtro = " AND removida_em IS NULL" if vigentes else ""
        if projeto_id is None:
            return self.sql(
                "SELECT * FROM designacoes_projeto_final WHERE hackathon_id = :h" + filtro,
                h=self.hackathon_id,
            )
        return self.sql(
            "SELECT * FROM designacoes_projeto_final WHERE submissao_id = :s" + filtro,
            s=projeto_id,
        )

    def avaliadores_do(self, projeto_id) -> set:
        return {linha["avaliador_id"] for linha in self.designacoes(projeto_id)}

    def designar(self, projeto_id, avaliador: dict):
        self.sql(
            "INSERT INTO designacoes_projeto_final"
            " (submissao_id, equipe_id, hackathon_id, avaliador_id) VALUES (:s, :e, :h, :a)",
            s=projeto_id,
            e=self.equipe_de[projeto_id],
            h=self.hackathon_id,
            a=avaliador["id"],
        )

    def mentorar(self, projeto_id, mentor: dict, encerrada: bool = False):
        self.sql(
            "INSERT INTO atribuicoes_mentor (id, equipe_id, hackathon_id, mentor_id, atribuido_por,"
            " encerrada_em, encerrada_por, motivo_encerramento) VALUES (:id, :e, :h, :m, :o,"
            + (" now(), :o, 'Troca')" if encerrada else " NULL, NULL, NULL)"),
            id=uuid4(),
            e=self.equipe_de[projeto_id],
            h=self.hackathon_id,
            m=mentor["id"],
            o=self.organizador["id"],
        )

    def tornar_integrante(self, projeto_id, usuario: dict):
        self.sql(
            "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id, funcao)"
            " VALUES (:e, :u, :h, 'DESENVOLVEDOR')",
            e=self.equipe_de[projeto_id],
            u=usuario["id"],
            h=self.hackathon_id,
        )

    def distribuir(self, client, quem=None):
        return client.post(
            f"/admin/hackathons/{self.hackathon_id}/avaliacao-tecnica/distribuir",
            headers=com_token((quem or self.organizador)["id"]),
        )

    def redistribuir(self, client, projeto_id, avaliadores, quem=None):
        return client.put(
            f"/admin/projetos-finais/{projeto_id}/avaliadores",
            json={
                "avaliador_ids": [str(a["id"] if isinstance(a, dict) else a) for a in avaliadores]
            },
            headers=com_token((quem or self.organizador)["id"]),
        )

    def conflito(self, client, projeto_id, avaliador, motivo="Orientador", quem=None):
        return client.post(
            f"/admin/hackathons/{self.hackathon_id}/avaliacao-tecnica/conflitos",
            json={
                "equipe_id": str(self.equipe_de[projeto_id]),
                "avaliador_id": str(avaliador["id"]),
                "motivo": motivo,
            },
            headers=com_token((quem or self.organizador)["id"]),
        )

    def limpar(self):
        h = self.hackathon_id
        self.sql("DELETE FROM designacoes_projeto_final WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM conflitos_projeto_final WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM atribuicoes_mentor WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM resultados_proposta WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM homologacoes_resultado WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM submissoes WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM temas WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM membros_equipe WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM equipes WHERE hackathon_id = :h", h=h)
        self.sql("DELETE FROM hackathon WHERE id = :h", h=h)
        if self.preexistentes:
            self.sql(
                "UPDATE usuarios SET ativo = true WHERE id = ANY(:ids)", ids=self.preexistentes
            )


@pytest.fixture
def tecnico(sql, usuario_no_banco):
    # Depende de usuario_no_banco: este teardown roda antes de apagar os usuários
    cenario = CenarioTecnico(sql, usuario_no_banco)
    try:
        yield cenario
    finally:
        cenario.limpar()


def carga(cenario) -> dict:
    total: dict = {}
    for linha in cenario.designacoes():
        total[linha["avaliador_id"]] = total.get(linha["avaliador_id"], 0) + 1
    return total


# ---------- configuração ----------


@pytest.mark.parametrize("quantidade", [2, 3])
def test_organizador_configura_a_quantidade(client, tecnico, sql, quantidade):
    resposta = client.patch(
        f"/admin/hackathons/{tecnico.hackathon_id}/avaliacao-tecnica/configuracao",
        json={"avaliadores_por_projeto_final": quantidade},
        headers=com_token(tecnico.organizador["id"]),
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {
        "hackathon_id": str(tecnico.hackathon_id),
        "avaliadores_por_projeto_final": quantidade,
    }
    linha = sql(
        "SELECT avaliadores_por_proposta, avaliadores_por_projeto_final FROM hackathon"
        " WHERE id = :h",
        h=tecnico.hackathon_id,
    )[0]
    assert linha["avaliadores_por_projeto_final"] == quantidade
    # Não se mistura com a configuração da avaliação científica
    assert linha["avaliadores_por_proposta"] is None


@pytest.mark.parametrize(
    "corpo", [{"avaliadores_por_projeto_final": v} for v in (0, 1, 4)] + [{}, {"x": 1}]
)
def test_quantidade_fora_de_2_a_3_e_recusada(client, tecnico, corpo):
    resposta = client.patch(
        f"/admin/hackathons/{tecnico.hackathon_id}/avaliacao-tecnica/configuracao",
        json=corpo,
        headers=com_token(tecnico.organizador["id"]),
    )

    assert resposta.status_code == 422


def test_banco_recusa_quantidade_fora_de_2_a_3(tecnico, sql):
    with pytest.raises(DBAPIError, match="ck_hackathon_avaliadores_por_projeto_final"):
        sql(
            "UPDATE hackathon SET avaliadores_por_projeto_final = 4 WHERE id = :h",
            h=tecnico.hackathon_id,
        )


def test_banco_recusa_duas_designacoes_vigentes_iguais(tecnico, sql):
    (projeto,) = tecnico.pronto(1, 1, 2)
    tecnico.designar(projeto, tecnico.avaliadores[0])

    with pytest.raises(DBAPIError, match="uq_designacoes_projeto_final_vigente"):
        tecnico.designar(projeto, tecnico.avaliadores[0])

    # Depois de removida, a mesma pessoa pode voltar a ser designada
    sql(
        "UPDATE designacoes_projeto_final SET removida_em = now(), removida_por = :o"
        " WHERE submissao_id = :s",
        o=tecnico.organizador["id"],
        s=projeto,
    )
    tecnico.designar(projeto, tecnico.avaliadores[0])


# ---------- distribuição ----------


@pytest.mark.parametrize("n", [2, 3])
def test_distribui_projetos_aprovados_de_forma_balanceada(client, tecnico, n):
    projetos = tecnico.pronto(5, 4, n)

    resposta = tecnico.distribuir(client)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {
        "hackathon_id": str(tecnico.hackathon_id),
        "avaliadores_por_projeto_final": n,
        "projetos_distribuidos": 5,
        "designacoes_criadas": 5 * n,
        "projetos_ja_completos": 0,
    }
    elegiveis = {a["id"] for a in tecnico.avaliadores}
    for projeto in projetos:
        designados = tecnico.avaliadores_do(projeto)
        assert len(designados) == n
        assert designados <= elegiveis
    cargas = [carga(tecnico).get(a["id"], 0) for a in tecnico.avaliadores]
    assert max(cargas) - min(cargas) <= 1
    for linha in tecnico.designacoes():
        assert linha["atribuido_por"] == tecnico.organizador["id"]
        assert linha["equipe_id"] == tecnico.equipe_de[linha["submissao_id"]]


def test_proposta_reprovada_nao_e_projeto_final(client, tecnico):
    tecnico.configurar(2)
    aprovado = tecnico.projeto()
    reprovado = tecnico.projeto(aprovada=False)
    tecnico.avaliador()
    tecnico.avaliador()

    resposta = tecnico.distribuir(client)

    assert resposta.json()["projetos_distribuidos"] == 1
    assert len(tecnico.avaliadores_do(aprovado)) == 2
    assert tecnico.avaliadores_do(reprovado) == set()


def test_distribuir_de_novo_so_completa(client, tecnico):
    projetos = tecnico.pronto(3, 3, 2)
    tecnico.distribuir(client)
    antes = sorted(str(d["id"]) for d in tecnico.designacoes())

    resposta = tecnico.distribuir(client)

    assert resposta.json()["designacoes_criadas"] == 0
    assert resposta.json()["projetos_ja_completos"] == len(projetos)
    assert sorted(str(d["id"]) for d in tecnico.designacoes()) == antes


def test_somente_comite_tecnico_ativo_e_elegivel(client, tecnico):
    tecnico.configurar(2)
    projeto = tecnico.projeto()
    a = tecnico.avaliador()
    b = tecnico.avaliador()
    tecnico.usuario_no_banco(papel="COMITE_CIENTIFICO", senha=None)
    tecnico.usuario_no_banco(papel="COMITE_TECNICO", senha=None, ativo=False)
    tecnico.usuario_no_banco(papel="COMITE_TECNICO", senha=None, situacao_conta="PENDENTE")

    assert tecnico.distribuir(client).status_code == 200
    assert tecnico.avaliadores_do(projeto) == {a["id"], b["id"]}


def test_sem_homologacao_cientifica_responde_409(client, tecnico):
    tecnico.configurar(2)
    tecnico.avaliador()
    tecnico.avaliador()

    resposta = tecnico.distribuir(client)

    assert resposta.status_code == 409
    assert "homologado" in resposta.json()["detail"]


def test_sem_quantidade_configurada_responde_409(client, tecnico):
    tecnico.projeto()
    tecnico.avaliador()
    tecnico.avaliador()

    resposta = tecnico.distribuir(client)

    assert resposta.status_code == 409
    assert tecnico.designacoes() == []


@pytest.mark.parametrize("status", ["FINALIZADO", "CANCELADO"])
def test_hackathon_encerrado_bloqueia(client, tecnico, status):
    (projeto,) = tecnico.pronto(1, 3, 2)
    tecnico.definir_status(status)

    assert tecnico.distribuir(client).status_code == 409
    assert tecnico.redistribuir(client, projeto, tecnico.avaliadores[:2]).status_code == 409
    assert tecnico.conflito(client, projeto, tecnico.avaliadores[0]).status_code == 409
    assert tecnico.designacoes() == []


def test_falta_de_avaliadores_nao_grava_nada(client, tecnico):
    tecnico.pronto(2, 2, 3)

    resposta = tecnico.distribuir(client)

    assert resposta.status_code == 409
    assert tecnico.designacoes() == []


# ---------- conflito de interesse (RN13) ----------


def test_mentor_da_equipe_nao_e_designado(client, tecnico):
    (projeto,) = tecnico.pronto(1, 3, 2)
    a, b, c = tecnico.avaliadores
    tecnico.mentorar(projeto, a)

    assert tecnico.distribuir(client).status_code == 200
    assert tecnico.avaliadores_do(projeto) == {b["id"], c["id"]}


def test_mentoria_encerrada_tambem_impede(client, tecnico):
    (projeto,) = tecnico.pronto(1, 3, 2)
    a, b, c = tecnico.avaliadores
    tecnico.mentorar(projeto, a, encerrada=True)

    tecnico.distribuir(client)

    assert a["id"] not in tecnico.avaliadores_do(projeto)


def test_integrante_da_equipe_nao_e_designado(client, tecnico):
    (projeto,) = tecnico.pronto(1, 3, 2)
    a, b, c = tecnico.avaliadores
    tecnico.tornar_integrante(projeto, b)

    tecnico.distribuir(client)

    assert tecnico.avaliadores_do(projeto) == {a["id"], c["id"]}


def test_conflito_declarado_impede_e_fica_registrado(client, tecnico, sql):
    (projeto,) = tecnico.pronto(1, 3, 2)
    a, b, c = tecnico.avaliadores

    resposta = tecnico.conflito(client, projeto, c, motivo="  Orientador de um integrante  ")

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["avaliador_id"] == str(c["id"])
    assert corpo["equipe_id"] == str(tecnico.equipe_de[projeto])
    assert corpo["motivo"] == "Orientador de um integrante"
    assert corpo["registrado_por"] == str(tecnico.organizador["id"])
    tecnico.distribuir(client)
    assert tecnico.avaliadores_do(projeto) == {a["id"], b["id"]}
    lista = client.get(
        f"/admin/hackathons/{tecnico.hackathon_id}/avaliacao-tecnica/conflitos",
        headers=com_token(tecnico.organizador["id"]),
    )
    assert [x["id"] for x in lista.json()] == [corpo["id"]]


def test_conflito_impede_quando_so_sobram_impedidos(client, tecnico):
    (projeto,) = tecnico.pronto(1, 2, 2)
    tecnico.mentorar(projeto, tecnico.avaliadores[0])

    resposta = tecnico.distribuir(client)

    assert resposta.status_code == 409
    assert tecnico.designacoes() == []


def test_conflito_repetido_ou_com_designacao_vigente_responde_409(client, tecnico):
    (projeto,) = tecnico.pronto(1, 3, 2)
    a, b, c = tecnico.avaliadores
    tecnico.designar(projeto, a)

    assert tecnico.conflito(client, projeto, a).status_code == 409
    assert tecnico.conflito(client, projeto, b).status_code == 201
    assert tecnico.conflito(client, projeto, b).status_code == 409


@pytest.mark.parametrize("motivo", ["", "   "])
def test_conflito_sem_motivo_responde_422(client, tecnico, motivo):
    (projeto,) = tecnico.pronto(1, 1, 2)

    assert tecnico.conflito(client, projeto, tecnico.avaliadores[0], motivo).status_code == 422


def test_conflito_com_quem_nao_e_tecnico_ou_equipe_de_outro_hackathon(client, tecnico, sql):
    (projeto,) = tecnico.pronto(1, 1, 2)
    cientifico = tecnico.usuario_no_banco(papel="COMITE_CIENTIFICO", senha=None)

    assert tecnico.conflito(client, projeto, cientifico).status_code == 404
    resposta = client.post(
        f"/admin/hackathons/{tecnico.hackathon_id}/avaliacao-tecnica/conflitos",
        json={
            "equipe_id": str(uuid4()),
            "avaliador_id": str(tecnico.avaliadores[0]["id"]),
            "motivo": "x",
        },
        headers=com_token(tecnico.organizador["id"]),
    )
    assert resposta.status_code == 404


# ---------- redistribuição ----------


def test_redistribui_e_mantem_historico(client, tecnico):
    (projeto,) = tecnico.pronto(1, 4, 2)
    a, b, c, d = tecnico.avaliadores
    tecnico.designar(projeto, a)
    tecnico.designar(projeto, b)
    original_a = next(x for x in tecnico.designacoes(projeto) if x["avaliador_id"] == a["id"])

    resposta = tecnico.redistribuir(client, projeto, [a, c])

    assert resposta.status_code == 200, resposta.text
    assert {x["id"] for x in resposta.json()["avaliadores"]} == {str(a["id"]), str(c["id"])}
    assert tecnico.avaliadores_do(projeto) == {a["id"], c["id"]}
    mantida = next(x for x in tecnico.designacoes(projeto) if x["avaliador_id"] == a["id"])
    assert mantida["id"] == original_a["id"]
    todas = tecnico.designacoes(projeto, vigentes=False)
    removida = next(x for x in todas if x["avaliador_id"] == b["id"])
    assert removida["removida_em"] is not None
    assert removida["removida_por"] == tecnico.organizador["id"]


def test_redistribuir_para_impedido_responde_409(client, tecnico):
    (projeto,) = tecnico.pronto(1, 3, 2)
    a, b, c = tecnico.avaliadores
    tecnico.mentorar(projeto, c)

    resposta = tecnico.redistribuir(client, projeto, [a, c])

    assert resposta.status_code == 409
    assert str(c["id"]) in resposta.json()["detail"]
    assert tecnico.designacoes(projeto) == []


@pytest.mark.parametrize("lista", ["repetido", "a_mais"])
def test_redistribuir_com_lista_invalida_responde_422(client, tecnico, lista):
    (projeto,) = tecnico.pronto(1, 3, 2)
    a, b, c = tecnico.avaliadores
    avaliadores = [a, a] if lista == "repetido" else [a, b, c]

    assert tecnico.redistribuir(client, projeto, avaliadores).status_code == 422


def test_redistribuir_com_nao_tecnico_responde_409(client, tecnico):
    (projeto,) = tecnico.pronto(1, 1, 2)
    cientifico = tecnico.usuario_no_banco(papel="COMITE_CIENTIFICO", senha=None)

    resposta = tecnico.redistribuir(client, projeto, [tecnico.avaliadores[0], cientifico])

    assert resposta.status_code == 409


def test_redistribuir_proposta_reprovada_responde_404(client, tecnico):
    tecnico.configurar(2)
    reprovado = tecnico.projeto(aprovada=False)
    tecnico.avaliador()
    tecnico.avaliador()

    assert tecnico.redistribuir(client, reprovado, tecnico.avaliadores).status_code == 404


def test_distribuicoes_simultaneas_nao_duplicam(client, tecnico):
    projetos = tecnico.pronto(4, 4, 3)
    barreira = Barrier(2)

    def disparar():
        barreira.wait()
        return tecnico.distribuir(client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        respostas = [f.result() for f in [pool.submit(disparar), pool.submit(disparar)]]

    assert [r.status_code for r in respostas] == [200, 200]
    assert sorted(r.json()["designacoes_criadas"] for r in respostas) == [0, 12]
    for projeto in projetos:
        assert len(tecnico.designacoes(projeto)) == 3


# ---------- consulta e permissões ----------


def test_listagem_admin_traz_avaliadores_vigentes(client, tecnico):
    projetos = tecnico.pronto(2, 2, 2)
    tecnico.designar(projetos[0], tecnico.avaliadores[0])

    resposta = client.get(
        f"/admin/hackathons/{tecnico.hackathon_id}/avaliacao-tecnica/designacoes",
        headers=com_token(tecnico.organizador["id"]),
    )

    assert resposta.status_code == 200
    por_projeto = {p["submissao_id"]: p for p in resposta.json()}
    assert [a["id"] for a in por_projeto[str(projetos[0])]["avaliadores"]] == [
        str(tecnico.avaliadores[0]["id"])
    ]
    assert por_projeto[str(projetos[1])]["avaliadores"] == []


def test_avaliador_ve_so_os_proprios_projetos(client, tecnico):
    p1, p2 = tecnico.pronto(2, 2, 2)
    a, b = tecnico.avaliadores
    tecnico.designar(p1, a)

    meus = client.get("/comite-tecnico/projetos-finais", headers=com_token(a["id"]))
    assert meus.status_code == 200
    assert [p["id"] for p in meus.json()] == [str(p1)]
    assert "equipe_id" not in meus.json()[0]
    assert (
        client.get(f"/comite-tecnico/projetos-finais/{p1}", headers=com_token(a["id"])).status_code
        == 200
    )
    assert (
        client.get(f"/comite-tecnico/projetos-finais/{p2}", headers=com_token(a["id"])).status_code
        == 404
    )
    assert (
        client.get(f"/comite-tecnico/projetos-finais/{p1}", headers=com_token(b["id"])).status_code
        == 404
    )


def test_designacao_removida_some_da_lista_do_avaliador(client, tecnico):
    (projeto,) = tecnico.pronto(1, 3, 2)
    a, b, c = tecnico.avaliadores
    tecnico.designar(projeto, a)
    tecnico.designar(projeto, b)
    tecnico.redistribuir(client, projeto, [b, c])

    resposta = client.get("/comite-tecnico/projetos-finais", headers=com_token(a["id"]))

    assert resposta.json() == []


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_CIENTIFICO", "COMITE_TECNICO"])
def test_somente_organizador_distribui(client, tecnico, papel):
    tecnico.pronto(1, 2, 2)
    outro = tecnico.usuario_no_banco(papel=papel, senha=None)

    assert tecnico.distribuir(client, quem=outro).status_code == 403
    assert tecnico.designacoes() == []


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_CIENTIFICO", "ORGANIZADOR"])
def test_somente_comite_tecnico_lista_os_proprios_projetos(client, tecnico, papel):
    outro = tecnico.usuario_no_banco(papel=papel, senha=None)

    resposta = client.get("/comite-tecnico/projetos-finais", headers=com_token(outro["id"]))

    assert resposta.status_code == 403


def test_sem_token_responde_401(client, tecnico):
    assert (
        client.post(
            f"/admin/hackathons/{tecnico.hackathon_id}/avaliacao-tecnica/distribuir"
        ).status_code
        == 401
    )
    assert client.get("/comite-tecnico/projetos-finais").status_code == 401
