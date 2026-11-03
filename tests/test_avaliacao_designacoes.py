"""BE-S4-09 (RF29): distribuição de propostas entre avaliadores, isolamento e redistribuição."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from tests.test_convites import com_token


class CenarioAvaliacao:
    """Hackathon ATIVO, propostas ENVIADA (uma equipe cada) e avaliadores do Comitê Científico.

    O banco de testes é compartilhado: os avaliadores elegíveis que já existem são desativados
    durante o teste (e reativados no fim), para que o conjunto de elegíveis seja só o criado aqui.
    """

    def __init__(self, sql, usuario_no_banco):
        self.sql = sql
        self.usuario_no_banco = usuario_no_banco
        self.preexistentes = [
            linha["id"]
            for linha in sql(
                "SELECT id FROM usuarios WHERE papel = 'COMITE_CIENTIFICO'"
                " AND ativo AND situacao_conta = 'ATIVA'"
            )
        ]
        if self.preexistentes:
            sql("UPDATE usuarios SET ativo = false WHERE id = ANY(:ids)", ids=self.preexistentes)
        self.hackathon_id = sql(
            "INSERT INTO hackathon (nome, status, data_inicio) VALUES"
            " ('Teste de designações', 'ATIVO', '2097-01-01') RETURNING id"
        )[0]["id"]
        self.tema_id = sql(
            "INSERT INTO temas (hackathon_id, titulo, ativo) VALUES (:h, 'Tema', true)"
            " RETURNING id",
            h=self.hackathon_id,
        )[0]["id"]
        self.organizador = usuario_no_banco(papel="ORGANIZADOR", senha=None)
        self.avaliadores: list[dict] = []

    def configurar(self, n: int | None):
        self.sql(
            "UPDATE hackathon SET avaliadores_por_proposta = :n WHERE id = :h",
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
        usuario = self.usuario_no_banco(papel="COMITE_CIENTIFICO", senha=None, **campos)
        self.avaliadores.append(usuario)
        return usuario

    def proposta(self, status: str = "ENVIADA"):
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
        if status == "ENVIADA":
            return self.sql(
                "INSERT INTO submissoes (equipe_id, hackathon_id, tema_id, status, titulo,"
                " descricao, ods, bases_dados, enviado_em) VALUES (:e, :h, :t, 'ENVIADA',"
                " 'Enviada', 'Descrição', '{1}', 'IBGE', now()) RETURNING id",
                e=equipe_id,
                h=self.hackathon_id,
                t=self.tema_id,
            )[0]["id"]
        return self.sql(
            "INSERT INTO submissoes (equipe_id, hackathon_id, status, titulo)"
            " VALUES (:e, :h, 'RASCUNHO', 'Rascunho') RETURNING id",
            e=equipe_id,
            h=self.hackathon_id,
        )[0]["id"]

    def pronto(self, propostas: int, avaliadores: int, n: int):
        """Configura N e cria as propostas ENVIADA e os avaliadores elegíveis."""
        self.configurar(n)
        ids = [self.proposta() for _ in range(propostas)]
        for _ in range(avaliadores):
            self.avaliador()
        return ids

    def designacoes(self, proposta_id=None):
        if proposta_id is None:
            return self.sql(
                "SELECT * FROM designacoes_avaliacao WHERE hackathon_id = :h", h=self.hackathon_id
            )
        return self.sql(
            "SELECT * FROM designacoes_avaliacao WHERE submissao_id = :s", s=proposta_id
        )

    def avaliadores_da(self, proposta_id) -> set:
        return {linha["avaliador_id"] for linha in self.designacoes(proposta_id)}

    def designar(self, proposta_id, avaliador: dict):
        self.sql(
            "INSERT INTO designacoes_avaliacao (submissao_id, hackathon_id, avaliador_id)"
            " VALUES (:s, :h, :a)",
            s=proposta_id,
            h=self.hackathon_id,
            a=avaliador["id"],
        )

    def dar_nota(self, proposta_id, avaliador: dict, nota=8):
        self.sql(
            "INSERT INTO avaliacoes (submissao_id, avaliador_id, nota, avaliado_em)"
            " VALUES (:s, :a, :n, now())",
            s=proposta_id,
            a=avaliador["id"],
            n=nota,
        )

    def distribuir(self, client, quem=None):
        return client.post(
            f"/admin/hackathons/{self.hackathon_id}/avaliacoes/distribuir",
            headers=com_token((quem or self.organizador)["id"]),
        )

    def redistribuir(self, client, proposta_id, avaliadores, quem=None):
        return client.put(
            f"/admin/propostas/{proposta_id}/avaliadores",
            json={
                "avaliador_ids": [str(a["id"] if isinstance(a, dict) else a) for a in avaliadores]
            },
            headers=com_token((quem or self.organizador)["id"]),
        )

    def listar(self, client, quem=None):
        return client.get(
            f"/admin/hackathons/{self.hackathon_id}/avaliacoes/designacoes",
            headers=com_token((quem or self.organizador)["id"]),
        )

    def limpar(self):
        h = self.hackathon_id
        self.sql(
            "DELETE FROM avaliacoes WHERE submissao_id IN"
            " (SELECT id FROM submissoes WHERE hackathon_id = :h)",
            h=h,
        )
        self.sql("DELETE FROM designacoes_avaliacao WHERE hackathon_id = :h", h=h)
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
def avaliacao(sql, usuario_no_banco):
    # Depende de usuario_no_banco: este teardown roda antes de apagar os usuários
    cenario = CenarioAvaliacao(sql, usuario_no_banco)
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


def test_quantidade_nasce_sem_valor_padrao(avaliacao, sql):
    linha = sql(
        "SELECT avaliadores_por_proposta FROM hackathon WHERE id = :h", h=avaliacao.hackathon_id
    )
    assert linha[0]["avaliadores_por_proposta"] is None


@pytest.mark.parametrize("quantidade", [2, 3])
def test_organizador_configura_a_quantidade(client, avaliacao, sql, quantidade):
    resposta = client.patch(
        f"/admin/hackathons/{avaliacao.hackathon_id}/avaliacao/configuracao",
        json={"avaliadores_por_proposta": quantidade},
        headers=com_token(avaliacao.organizador["id"]),
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {
        "hackathon_id": str(avaliacao.hackathon_id),
        "avaliadores_por_proposta": quantidade,
    }
    linha = sql(
        "SELECT avaliadores_por_proposta FROM hackathon WHERE id = :h", h=avaliacao.hackathon_id
    )
    assert linha[0]["avaliadores_por_proposta"] == quantidade


@pytest.mark.parametrize(
    "corpo", [{"avaliadores_por_proposta": v} for v in (0, 1, 4)] + [{}, {"x": 1}]
)
def test_quantidade_fora_de_2_a_3_e_recusada(client, avaliacao, corpo):
    avaliacao.configurar(2)

    resposta = client.patch(
        f"/admin/hackathons/{avaliacao.hackathon_id}/avaliacao/configuracao",
        json=corpo,
        headers=com_token(avaliacao.organizador["id"]),
    )

    assert resposta.status_code == 422


def test_configurar_hackathon_inexistente(client, avaliacao):
    resposta = client.patch(
        f"/admin/hackathons/{uuid4()}/avaliacao/configuracao",
        json={"avaliadores_por_proposta": 2},
        headers=com_token(avaliacao.organizador["id"]),
    )

    assert resposta.status_code == 404


def test_banco_recusa_quantidade_fora_de_2_a_3(avaliacao, sql):
    with pytest.raises(DBAPIError, match="ck_hackathon_avaliadores_por_proposta"):
        sql(
            "UPDATE hackathon SET avaliadores_por_proposta = 1 WHERE id = :h",
            h=avaliacao.hackathon_id,
        )


def test_banco_recusa_designacao_duplicada(avaliacao):
    (proposta,) = avaliacao.pronto(1, 1, 2)
    avaliacao.designar(proposta, avaliacao.avaliadores[0])

    with pytest.raises(DBAPIError, match="uq_designacoes_submissao_avaliador"):
        avaliacao.designar(proposta, avaliacao.avaliadores[0])


def test_alterar_quantidade_nao_mexe_nas_designacoes_existentes(client, avaliacao):
    propostas = avaliacao.pronto(3, 4, 2)
    assert avaliacao.distribuir(client).status_code == 200
    antes = {p: avaliacao.avaliadores_da(p) for p in propostas}

    resposta = client.patch(
        f"/admin/hackathons/{avaliacao.hackathon_id}/avaliacao/configuracao",
        json={"avaliadores_por_proposta": 3},
        headers=com_token(avaliacao.organizador["id"]),
    )

    assert resposta.status_code == 200
    assert {p: avaliacao.avaliadores_da(p) for p in propostas} == antes
    # Só uma nova distribuição completa as propostas até o novo valor, sem tirar ninguém
    assert avaliacao.distribuir(client).json()["designacoes_criadas"] == 3
    for p in propostas:
        depois = avaliacao.avaliadores_da(p)
        assert len(depois) == 3
        assert antes[p] <= depois


# ---------- distribuição ----------


@pytest.mark.parametrize("n", [2, 3])
def test_distribui_a_quantidade_configurada_de_forma_balanceada(client, avaliacao, n):
    propostas = avaliacao.pronto(5, 4, n)

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {
        "hackathon_id": str(avaliacao.hackathon_id),
        "avaliadores_por_proposta": n,
        "propostas_distribuidas": 5,
        "designacoes_criadas": 5 * n,
        "propostas_ja_completas": 0,
    }
    elegiveis = {a["id"] for a in avaliacao.avaliadores}
    for proposta in propostas:
        designados = avaliacao.avaliadores_da(proposta)
        assert len(designados) == n
        assert designados <= elegiveis
    cargas = [carga(avaliacao).get(a["id"], 0) for a in avaliacao.avaliadores]
    assert sum(cargas) == 5 * n
    assert max(cargas) - min(cargas) <= 1
    for linha in avaliacao.designacoes():
        assert linha["atribuido_por"] == avaliacao.organizador["id"]
        assert linha["atribuido_em"] is not None


def test_distribuir_de_novo_nao_altera_o_que_ja_esta_completo(client, avaliacao):
    propostas = avaliacao.pronto(3, 3, 2)
    avaliacao.distribuir(client)
    antes = sorted(str(d["id"]) for d in avaliacao.designacoes())

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 200
    assert resposta.json()["designacoes_criadas"] == 0
    assert resposta.json()["propostas_ja_completas"] == len(propostas)
    assert sorted(str(d["id"]) for d in avaliacao.designacoes()) == antes


def test_nova_proposta_enviada_e_incluida_na_proxima_distribuicao(client, avaliacao):
    avaliacao.pronto(2, 3, 2)
    avaliacao.distribuir(client)
    nova = avaliacao.proposta()

    resposta = avaliacao.distribuir(client)

    assert resposta.json()["propostas_distribuidas"] == 1
    assert resposta.json()["designacoes_criadas"] == 2
    assert len(avaliacao.avaliadores_da(nova)) == 2


def test_rascunho_nao_e_distribuido(client, avaliacao):
    (enviada,) = avaliacao.pronto(1, 3, 2)
    rascunho = avaliacao.proposta("RASCUNHO")

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 200
    assert resposta.json()["propostas_distribuidas"] == 1
    assert len(avaliacao.avaliadores_da(enviada)) == 2
    assert avaliacao.avaliadores_da(rascunho) == set()


def test_rascunho_nao_pode_ser_redistribuido(client, avaliacao):
    avaliacao.pronto(0, 3, 2)
    rascunho = avaliacao.proposta("RASCUNHO")

    resposta = avaliacao.redistribuir(client, rascunho, avaliacao.avaliadores[:2])

    assert resposta.status_code == 409
    assert avaliacao.designacoes() == []


def test_distribuir_sem_quantidade_configurada_responde_409(client, avaliacao):
    avaliacao.pronto(2, 3, 2)
    avaliacao.configurar(None)

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 409
    assert avaliacao.designacoes() == []


def test_avaliadores_insuficientes_nao_gravam_nada(client, avaliacao):
    avaliacao.pronto(3, 2, 3)

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 409
    assert avaliacao.designacoes() == []


def test_insuficiencia_so_numa_proposta_tambem_desfaz_tudo(client, avaliacao):
    # Duas avaliadoras bastam para N=2; com N=3 e uma proposta já com 2, falta quem complete
    propostas = avaliacao.pronto(2, 2, 3)
    avaliacao.designar(propostas[1], avaliacao.avaliadores[0])
    avaliacao.designar(propostas[1], avaliacao.avaliadores[1])

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 409
    assert len(avaliacao.designacoes()) == 2
    assert avaliacao.avaliadores_da(propostas[0]) == set()


@pytest.mark.parametrize(
    "ajuste",
    [
        {"ativo": False},
        {"situacao_conta": "PENDENTE"},
    ],
    ids=["desativado", "conta-pendente"],
)
def test_avaliador_inativo_ou_pendente_nao_e_elegivel(client, avaliacao, ajuste):
    avaliacao.pronto(1, 2, 2)
    inelegivel = avaliacao.avaliador(**ajuste)

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 200
    assert inelegivel["id"] not in {d["avaliador_id"] for d in avaliacao.designacoes()}


def test_outros_papeis_e_dev_nao_sao_avaliadores(client, avaliacao):
    avaliacao.pronto(1, 2, 2)
    for papel in ["DEV", "COMITE_TECNICO", "ORGANIZADOR", "MENTOR", "PARTICIPANTE"]:
        avaliacao.usuario_no_banco(papel=papel, senha=None)

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 200
    assert {d["avaliador_id"] for d in avaliacao.designacoes()} == {
        a["id"] for a in avaliacao.avaliadores
    }


@pytest.mark.parametrize("status", ["EM_AVALIACAO", "FINALIZADO", "CANCELADO"])
def test_distribuir_bloqueado_apos_inicio_da_avaliacao(client, avaliacao, status):
    avaliacao.pronto(2, 3, 2)
    avaliacao.definir_status(status)

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 409
    assert avaliacao.designacoes() == []


@pytest.mark.parametrize("status", ["INSCRICOES_ENCERRADAS", "ATIVO"])
def test_distribuir_permitido_antes_da_avaliacao(client, avaliacao, status):
    avaliacao.pronto(1, 2, 2)
    avaliacao.definir_status(status)

    assert avaliacao.distribuir(client).status_code == 200


def test_distribuir_ignora_proposta_que_ja_tem_nota(client, avaliacao):
    com_nota, sem_nota = avaliacao.pronto(2, 3, 2)
    avaliacao.designar(com_nota, avaliacao.avaliadores[0])
    avaliacao.dar_nota(com_nota, avaliacao.avaliadores[0])

    resposta = avaliacao.distribuir(client)

    assert resposta.status_code == 200
    assert len(avaliacao.avaliadores_da(com_nota)) == 1
    assert len(avaliacao.avaliadores_da(sem_nota)) == 2


def test_distribuir_hackathon_inexistente(client, avaliacao):
    resposta = client.post(
        f"/admin/hackathons/{uuid4()}/avaliacoes/distribuir",
        headers=com_token(avaliacao.organizador["id"]),
    )

    assert resposta.status_code == 404


def test_distribuicoes_simultaneas_nao_duplicam_designacoes(client, avaliacao):
    propostas = avaliacao.pronto(4, 4, 3)
    barreira = Barrier(2)

    def disparar():
        barreira.wait()
        return avaliacao.distribuir(client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        respostas = [f.result() for f in [pool.submit(disparar), pool.submit(disparar)]]

    assert [r.status_code for r in respostas] == [200, 200]
    assert sorted(r.json()["designacoes_criadas"] for r in respostas) == [0, 12]
    for proposta in propostas:
        assert len(avaliacao.designacoes(proposta)) == 3


# ---------- redistribuição ----------


def test_redistribui_antes_de_a_avaliacao_comecar(client, avaliacao):
    (proposta,) = avaliacao.pronto(1, 4, 2)
    a, b, c, d = avaliacao.avaliadores
    avaliacao.designar(proposta, a)
    avaliacao.designar(proposta, b)
    original_a = next(x for x in avaliacao.designacoes(proposta) if x["avaliador_id"] == a["id"])

    resposta = avaliacao.redistribuir(client, proposta, [a, c])

    assert resposta.status_code == 200, resposta.text
    assert avaliacao.avaliadores_da(proposta) == {a["id"], c["id"]}
    assert {x["id"] for x in resposta.json()["avaliadores"]} == {str(a["id"]), str(c["id"])}
    # Quem continua mantém a designação original
    atual_a = next(x for x in avaliacao.designacoes(proposta) if x["avaliador_id"] == a["id"])
    assert atual_a["id"] == original_a["id"]
    assert [d for d in avaliacao.designacoes(proposta) if d["avaliador_id"] == c["id"]][0][
        "atribuido_por"
    ] == avaliacao.organizador["id"]


def test_redistribui_proposta_ainda_sem_designacao(client, avaliacao):
    (proposta,) = avaliacao.pronto(1, 3, 3)

    resposta = avaliacao.redistribuir(client, proposta, avaliacao.avaliadores)

    assert resposta.status_code == 200
    assert avaliacao.avaliadores_da(proposta) == {a["id"] for a in avaliacao.avaliadores}


def test_redistribuir_so_afeta_a_proposta_indicada(client, avaliacao):
    p1, p2 = avaliacao.pronto(2, 3, 2)
    avaliacao.distribuir(client)
    outra = avaliacao.avaliadores_da(p2)
    novos = [a for a in avaliacao.avaliadores if a["id"] not in avaliacao.avaliadores_da(p1)]
    assert novos  # há pelo menos um avaliador novo para a proposta 1

    resposta = avaliacao.redistribuir(client, p1, avaliacao.avaliadores[:2])

    assert resposta.status_code == 200
    assert avaliacao.avaliadores_da(p2) == outra


@pytest.mark.parametrize("status", ["EM_AVALIACAO", "FINALIZADO", "CANCELADO"])
def test_redistribuir_bloqueado_depois_do_inicio_da_avaliacao(client, avaliacao, status):
    (proposta,) = avaliacao.pronto(1, 3, 2)
    a, b, c = avaliacao.avaliadores
    avaliacao.designar(proposta, a)
    avaliacao.designar(proposta, b)
    avaliacao.definir_status(status)

    resposta = avaliacao.redistribuir(client, proposta, [a, c])

    assert resposta.status_code == 409
    assert avaliacao.avaliadores_da(proposta) == {a["id"], b["id"]}


def test_redistribuir_bloqueado_se_a_proposta_ja_tem_nota(client, avaliacao):
    (proposta,) = avaliacao.pronto(1, 3, 2)
    a, b, c = avaliacao.avaliadores
    avaliacao.designar(proposta, a)
    avaliacao.designar(proposta, b)
    avaliacao.dar_nota(proposta, a)

    resposta = avaliacao.redistribuir(client, proposta, [b, c])

    assert resposta.status_code == 409
    assert avaliacao.avaliadores_da(proposta) == {a["id"], b["id"]}


def test_redistribuir_sem_quantidade_configurada(client, avaliacao):
    (proposta,) = avaliacao.pronto(1, 2, 2)
    avaliacao.configurar(None)

    assert avaliacao.redistribuir(client, proposta, avaliacao.avaliadores).status_code == 409


@pytest.mark.parametrize("quantos", [1, 3])
def test_redistribuir_exige_exatamente_a_quantidade_configurada(client, avaliacao, quantos):
    (proposta,) = avaliacao.pronto(1, 3, 2)
    a, b, c = avaliacao.avaliadores
    avaliacao.designar(proposta, a)
    avaliacao.designar(proposta, b)

    resposta = client.put(
        f"/admin/propostas/{proposta}/avaliadores",
        json={"avaliador_ids": [str(x["id"]) for x in avaliacao.avaliadores[:quantos]]},
        headers=com_token(avaliacao.organizador["id"]),
    )

    assert resposta.status_code == 422
    assert avaliacao.avaliadores_da(proposta) == {a["id"], b["id"]}


def test_redistribuir_recusa_avaliador_repetido(client, avaliacao):
    (proposta,) = avaliacao.pronto(1, 2, 2)
    a = avaliacao.avaliadores[0]

    resposta = avaliacao.redistribuir(client, proposta, [a, a])

    assert resposta.status_code == 422
    assert avaliacao.designacoes() == []


@pytest.mark.parametrize(
    "tipo", ["dev", "participante", "comite-tecnico", "desativado", "pendente", "inexistente"]
)
def test_redistribuir_recusa_quem_nao_e_avaliador_elegivel(client, avaliacao, tipo):
    (proposta,) = avaliacao.pronto(1, 2, 2)
    a, b = avaliacao.avaliadores
    avaliacao.designar(proposta, a)
    avaliacao.designar(proposta, b)
    if tipo == "inexistente":
        intruso = uuid4()
    else:
        intruso = avaliacao.usuario_no_banco(
            papel={
                "dev": "DEV",
                "participante": "PARTICIPANTE",
                "comite-tecnico": "COMITE_TECNICO",
            }.get(tipo, "COMITE_CIENTIFICO"),
            senha=None,
            ativo=tipo != "desativado",
            situacao_conta="PENDENTE" if tipo == "pendente" else "ATIVA",
        )

    resposta = avaliacao.redistribuir(client, proposta, [a, intruso])

    assert resposta.status_code == 409
    assert avaliacao.avaliadores_da(proposta) == {a["id"], b["id"]}


def test_redistribuir_proposta_inexistente(client, avaliacao):
    avaliacao.pronto(0, 2, 2)

    assert avaliacao.redistribuir(client, uuid4(), avaliacao.avaliadores).status_code == 404


# ---------- listagem do organizador ----------


def test_organizador_lista_designacoes_com_propostas_ainda_sem_avaliador(client, avaliacao):
    p1, p2 = avaliacao.pronto(2, 3, 2)
    avaliacao.proposta("RASCUNHO")
    avaliacao.designar(p1, avaliacao.avaliadores[0])
    avaliacao.designar(p1, avaliacao.avaliadores[1])

    resposta = avaliacao.listar(client)

    assert resposta.status_code == 200, resposta.text
    por_proposta = {item["submissao_id"]: item for item in resposta.json()}
    assert set(por_proposta) == {str(p1), str(p2)}  # rascunho fora
    assert {x["id"] for x in por_proposta[str(p1)]["avaliadores"]} == {
        str(a["id"]) for a in avaliacao.avaliadores[:2]
    }
    assert por_proposta[str(p2)]["avaliadores"] == []


def test_listar_designacoes_de_hackathon_inexistente(client, avaliacao):
    resposta = client.get(
        f"/admin/hackathons/{uuid4()}/avaliacoes/designacoes",
        headers=com_token(avaliacao.organizador["id"]),
    )

    assert resposta.status_code == 404


# ---------- isolamento por avaliador ----------


def test_avaliador_ve_somente_as_propostas_designadas_a_ele(client, avaliacao):
    p1, p2, p3 = avaliacao.pronto(3, 2, 2)
    a, b = avaliacao.avaliadores
    avaliacao.designar(p1, a)
    avaliacao.designar(p2, b)
    avaliacao.designar(p3, a)
    avaliacao.designar(p3, b)

    lista_a = client.get("/avaliador/propostas", headers=com_token(a["id"]))
    lista_b = client.get("/avaliador/propostas", headers=com_token(b["id"]))

    assert lista_a.status_code == 200
    assert {x["id"] for x in lista_a.json()} == {str(p1), str(p3)}
    assert {x["id"] for x in lista_b.json()} == {str(p2), str(p3)}


def test_avaliador_consulta_proposta_designada_sem_ver_a_equipe(client, avaliacao):
    (proposta,) = avaliacao.pronto(1, 2, 2)
    a = avaliacao.avaliadores[0]
    avaliacao.designar(proposta, a)

    resposta = client.get(f"/avaliador/propostas/{proposta}", headers=com_token(a["id"]))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["id"] == str(proposta)
    assert corpo["titulo"] == "Enviada"
    assert corpo["descricao"] == "Descrição"
    assert "equipe_id" not in corpo


def test_proposta_de_outro_avaliador_ou_inexistente_responde_404(client, avaliacao):
    p1, p2 = avaliacao.pronto(2, 2, 2)
    a, b = avaliacao.avaliadores
    avaliacao.designar(p1, a)
    avaliacao.designar(p2, b)

    alheia = client.get(f"/avaliador/propostas/{p2}", headers=com_token(a["id"]))
    inexistente = client.get(f"/avaliador/propostas/{uuid4()}", headers=com_token(a["id"]))

    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.json() == inexistente.json()  # não revela que a proposta existe


def test_avaliador_sem_designacao_recebe_lista_vazia(client, avaliacao):
    avaliacao.pronto(2, 2, 2)

    resposta = client.get("/avaliador/propostas", headers=com_token(avaliacao.avaliadores[0]["id"]))

    assert resposta.status_code == 200
    assert resposta.json() == []


def test_redistribuir_tira_o_acesso_de_quem_saiu(client, avaliacao):
    (proposta,) = avaliacao.pronto(1, 3, 2)
    a, b, c = avaliacao.avaliadores
    avaliacao.designar(proposta, a)
    avaliacao.designar(proposta, b)
    assert (
        client.get(f"/avaliador/propostas/{proposta}", headers=com_token(b["id"])).status_code
        == 200
    )

    avaliacao.redistribuir(client, proposta, [a, c])

    assert (
        client.get(f"/avaliador/propostas/{proposta}", headers=com_token(b["id"])).status_code
        == 404
    )
    assert (
        client.get(f"/avaliador/propostas/{proposta}", headers=com_token(c["id"])).status_code
        == 200
    )


def test_dev_nas_rotas_do_avaliador_ve_so_o_que_foi_designado_a_ele(client, avaliacao):
    (proposta,) = avaliacao.pronto(1, 2, 2)
    avaliacao.distribuir(client)
    dev = avaliacao.usuario_no_banco(papel="DEV", senha=None)

    assert client.get("/avaliador/propostas", headers=com_token(dev["id"])).json() == []
    assert (
        client.get(f"/avaliador/propostas/{proposta}", headers=com_token(dev["id"])).status_code
        == 404
    )


# ---------- perfis e autenticação ----------


@pytest.mark.parametrize("papel", ["COMITE_CIENTIFICO", "COMITE_TECNICO", "MENTOR", "PARTICIPANTE"])
def test_perfis_sem_permissao_nas_rotas_do_organizador(client, avaliacao, papel):
    (proposta,) = avaliacao.pronto(1, 2, 2)
    usuario = avaliacao.usuario_no_banco(papel=papel, senha=None)
    headers = com_token(usuario["id"])
    h = avaliacao.hackathon_id

    respostas = [
        client.patch(
            f"/admin/hackathons/{h}/avaliacao/configuracao",
            json={"avaliadores_por_proposta": 3},
            headers=headers,
        ),
        client.post(f"/admin/hackathons/{h}/avaliacoes/distribuir", headers=headers),
        client.put(
            f"/admin/propostas/{proposta}/avaliadores",
            json={"avaliador_ids": [str(a["id"]) for a in avaliacao.avaliadores]},
            headers=headers,
        ),
        client.get(f"/admin/hackathons/{h}/avaliacoes/designacoes", headers=headers),
    ]

    assert [r.status_code for r in respostas] == [403] * 4
    assert avaliacao.designacoes() == []


@pytest.mark.parametrize("papel", ["ORGANIZADOR", "COMITE_TECNICO", "MENTOR", "PARTICIPANTE"])
def test_perfis_sem_permissao_nas_rotas_do_avaliador(client, avaliacao, papel):
    (proposta,) = avaliacao.pronto(1, 2, 2)
    avaliacao.distribuir(client)
    usuario = avaliacao.usuario_no_banco(papel=papel, senha=None)
    headers = com_token(usuario["id"])

    assert client.get("/avaliador/propostas", headers=headers).status_code == 403
    assert client.get(f"/avaliador/propostas/{proposta}", headers=headers).status_code == 403


def test_dev_organiza_a_distribuicao(client, avaliacao):
    avaliacao.pronto(1, 2, 2)
    dev = avaliacao.usuario_no_banco(papel="DEV", senha=None)

    assert avaliacao.distribuir(client, quem=dev).status_code == 200
    assert avaliacao.listar(client, quem=dev).status_code == 200


@pytest.mark.parametrize("acesso", ["sem-token", "token-invalido", "conta-pendente", "desativado"])
def test_autenticacao_e_conta_ativa(client, avaliacao, acesso):
    (proposta,) = avaliacao.pronto(1, 2, 2)
    if acesso == "sem-token":
        headers = {}
    elif acesso == "token-invalido":
        headers = {"Authorization": "Bearer invalido"}
    else:
        usuario = avaliacao.usuario_no_banco(
            papel="ORGANIZADOR",
            senha=None,
            situacao_conta="PENDENTE" if acesso == "conta-pendente" else "ATIVA",
            ativo=acesso != "desativado",
        )
        headers = com_token(usuario["id"])
    esperado = 403 if acesso == "conta-pendente" else 401

    respostas = [
        client.post(
            f"/admin/hackathons/{avaliacao.hackathon_id}/avaliacoes/distribuir", headers=headers
        ),
        client.get("/avaliador/propostas", headers=headers),
        client.get(f"/avaliador/propostas/{proposta}", headers=headers),
    ]

    assert [r.status_code for r in respostas] == [esperado] * 3
    assert avaliacao.designacoes() == []
