"""
Conferência do comprovante de vínculo e reenvio depois de recusa (BE-S4-05: RF21, RN25).

Grava no banco; a fixture `fila` apaga o que criou.
"""

from uuid import uuid4

import pytest

from tests.test_convites import com_token

LINK = "https://res.cloudinary.com/demo/novo-comprovante.pdf"


class Fila:
    def __init__(self, sql, usuario_no_banco, hackathon_id):
        self.sql = sql
        self.usuario_no_banco = usuario_no_banco
        self.hackathon_id = hackathon_id
        self.organizador = usuario_no_banco(papel="ORGANIZADOR")

    def enviar(self, status: str = "PENDENTE", *, conta: str = "PENDENTE") -> tuple[dict, str]:
        """Participante com conta `conta` e um comprovante no estado pedido."""
        usuario = self.usuario_no_banco(situacao_conta=conta)
        return usuario, self.comprovante(usuario, status)

    def comprovante(self, usuario: dict, status: str = "PENDENTE") -> str:
        decidido = status != "PENDENTE"
        return str(
            self.sql(
                "INSERT INTO comprovantes_vinculo (usuario_id, hackathon_id, arquivo_url, status,"
                " motivo_recusa, validado_em) VALUES (:u, :h, 'https://x.com/c.pdf',"
                " CAST(:s AS status_comprovante), :m, CASE WHEN :d THEN now() END) RETURNING id",
                u=usuario["id"],
                h=self.hackathon_id,
                s=status,
                m="Ilegível" if status == "RECUSADO" else None,
                d=decidido,
            )[0]["id"]
        )

    def linha(self, comprovante_id: str) -> dict:
        return self.sql("SELECT * FROM comprovantes_vinculo WHERE id = :c", c=comprovante_id)[0]

    def conta(self, usuario: dict) -> str:
        return self.sql(
            "SELECT situacao_conta::text AS s FROM usuarios WHERE id = :u", u=usuario["id"]
        )[0]["s"]

    def decidir(self, client, comprovante_id: str, acao: str, quem=None, **json):
        return client.post(
            f"/admin/comprovantes/{comprovante_id}/{acao}",
            headers=com_token((quem or self.organizador)["id"]),
            json=json or None,
        )

    def listar(self, client, quem=None, **params):
        return client.get(
            "/admin/comprovantes",
            params={"hackathon_id": str(self.hackathon_id), **params},
            headers=com_token((quem or self.organizador)["id"]),
        )


@pytest.fixture
def fila(sql, usuario_no_banco, hackathon_aberto):
    return Fila(sql, usuario_no_banco, hackathon_aberto)


# --- Fila de conferência ---


def test_fila_traz_so_os_pendentes_com_o_arquivo_e_quem_enviou(client, fila, sql):
    usuario, pendente = fila.enviar()
    sql(
        "UPDATE usuarios SET nome = 'Ana Souza', instituicao = 'UFPA', curso = 'SI',"
        " periodo = 5 WHERE id = :u",
        u=usuario["id"],
    )
    fila.enviar("APROVADO", conta="ATIVA")
    fila.enviar("RECUSADO")

    resposta = fila.listar(client)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert [c["id"] for c in corpo] == [pendente]
    item = corpo[0]
    assert item["arquivo_url"] == "https://x.com/c.pdf"
    assert item["status"] == "PENDENTE"
    assert item["usuario"] == {
        "id": str(usuario["id"]),
        "nome": "Ana Souza",
        "email": usuario["email"],
        "instituicao": "UFPA",
        "curso": "SI",
        "periodo": 5,
    }
    assert "senha_hash" not in resposta.text


def test_fila_ordena_do_mais_antigo_e_pagina(client, fila):
    ids = [fila.enviar()[1] for _ in range(3)]

    todos = [c["id"] for c in fila.listar(client).json()]
    pagina = [c["id"] for c in fila.listar(client, limite=1, deslocamento=1).json()]

    assert todos == ids
    assert pagina == [ids[1]]


@pytest.mark.parametrize("situacao", ["APROVADO", "RECUSADO"])
def test_fila_filtra_por_situacao(client, fila, situacao):
    fila.enviar()
    _, decidido = fila.enviar(situacao)

    assert [c["id"] for c in fila.listar(client, status=situacao).json()] == [decidido]


def test_fila_filtra_por_hackathon(client, fila):
    fila.enviar()

    resposta = client.get(
        "/admin/comprovantes",
        params={"hackathon_id": str(uuid4())},
        headers=com_token(fila.organizador["id"]),
    )

    assert resposta.json() == []


@pytest.mark.parametrize("papel", ["ORGANIZADOR", "COMITE_CIENTIFICO", "DEV"])
def test_quem_confere_comprovantes(client, fila, papel):
    fila.enviar()

    assert fila.listar(client, quem=fila.usuario_no_banco(papel=papel)).status_code == 200


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO"])
def test_outros_perfis_nao_conferem(client, fila, papel):
    _, comprovante = fila.enviar()
    intruso = fila.usuario_no_banco(papel=papel)

    assert fila.listar(client, quem=intruso).status_code == 403
    assert fila.decidir(client, comprovante, "aprovar", quem=intruso).status_code == 403
    assert (
        fila.decidir(client, comprovante, "recusar", quem=intruso, motivo_recusa="x").status_code
        == 403
    )
    assert fila.linha(comprovante)["status"] == "PENDENTE"


def test_fila_exige_login(client, fila):
    assert client.get("/admin/comprovantes").status_code == 401


# --- Aprovar ---


def test_aprovar_registra_quem_validou_e_ativa_a_conta(client, fila):
    usuario, comprovante = fila.enviar()
    assert fila.conta(usuario) == "PENDENTE"

    resposta = fila.decidir(client, comprovante, "aprovar")

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "APROVADO"
    linha = fila.linha(comprovante)
    assert linha["status"] == "APROVADO"
    assert linha["validado_por"] == fila.organizador["id"]
    assert linha["validado_em"] is not None
    assert linha["motivo_recusa"] is None
    assert fila.conta(usuario) == "ATIVA"
    # Com a conta ativa, a pessoa já usa o resto da API
    assert client.get("/equipes/minhas", headers=com_token(usuario["id"])).status_code == 200


def test_aprovar_duas_vezes_ou_decidir_o_decidido(client, fila):
    _, comprovante = fila.enviar()
    assert fila.decidir(client, comprovante, "aprovar").status_code == 200

    assert fila.decidir(client, comprovante, "aprovar").status_code == 409
    assert fila.decidir(client, comprovante, "recusar", motivo_recusa="Tarde").status_code == 409
    assert fila.linha(comprovante)["status"] == "APROVADO"


def test_comprovante_inexistente(client, fila):
    assert fila.decidir(client, str(uuid4()), "aprovar").status_code == 404
    assert fila.decidir(client, str(uuid4()), "recusar", motivo_recusa="x").status_code == 404


# --- Recusar ---


def test_recusar_exige_o_motivo(client, fila):
    _, comprovante = fila.enviar()

    for corpo in ({}, {"motivo_recusa": ""}, {"motivo_recusa": "   "}, {"motivo_recusa": None}):
        assert fila.decidir(client, comprovante, "recusar", **corpo).status_code == 422
    assert fila.linha(comprovante)["status"] == "PENDENTE"


def test_recusar_guarda_o_motivo_e_mantem_a_conta_pendente(client, fila):
    usuario, comprovante = fila.enviar()

    resposta = fila.decidir(client, comprovante, "recusar", motivo_recusa="  Documento ilegível ")

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["motivo_recusa"] == "Documento ilegível"
    linha = fila.linha(comprovante)
    assert (linha["status"], linha["motivo_recusa"]) == ("RECUSADO", "Documento ilegível")
    assert linha["validado_por"] == fila.organizador["id"]
    assert fila.conta(usuario) == "PENDENTE"


# --- A pessoa recusada acompanha e reenvia (Q25) ---


def test_recusado_ve_o_motivo_com_a_conta_pendente_e_reenvia(client, fila):
    usuario, comprovante = fila.enviar()
    fila.decidir(client, comprovante, "recusar", motivo_recusa="Documento ilegível")
    cabecalho = com_token(usuario["id"])

    # A conta segue pendente e barrada no resto da API, mas estas duas rotas funcionam
    assert client.get("/equipes/minhas", headers=cabecalho).status_code == 403
    meus = client.get("/comprovantes/meus", headers=cabecalho)
    assert meus.status_code == 200
    assert [(c["status"], c["motivo_recusa"]) for c in meus.json()] == [
        ("RECUSADO", "Documento ilegível")
    ]

    novo = client.post("/comprovantes", json={"arquivo_url": LINK}, headers=cabecalho)

    assert novo.status_code == 201, novo.text
    assert novo.json()["status"] == "PENDENTE"
    assert novo.json()["arquivo_url"] == LINK
    assert novo.json()["hackathon_id"] == str(fila.hackathon_id)
    historico = client.get("/comprovantes/meus", headers=cabecalho).json()
    assert [c["status"] for c in historico] == ["PENDENTE", "RECUSADO"]
    # O novo comprovante entra na fila de conferência
    assert [c["id"] for c in fila.listar(client).json()] == [novo.json()["id"]]


def test_reenvio_aprovado_ativa_a_conta(client, fila):
    usuario, comprovante = fila.enviar()
    fila.decidir(client, comprovante, "recusar", motivo_recusa="Ilegível")
    cabecalho = com_token(usuario["id"])
    novo = client.post("/comprovantes", json={"arquivo_url": LINK}, headers=cabecalho).json()

    assert fila.decidir(client, novo["id"], "aprovar").status_code == 200
    assert fila.conta(usuario) == "ATIVA"


@pytest.mark.parametrize("status", ["PENDENTE", "APROVADO"])
def test_nao_reenvia_com_comprovante_pendente_ou_aprovado(client, fila, status):
    usuario, _ = fila.enviar(status)

    resposta = client.post(
        "/comprovantes", json={"arquivo_url": LINK}, headers=com_token(usuario["id"])
    )

    assert resposta.status_code == 409
    assert len(client.get("/comprovantes/meus", headers=com_token(usuario["id"])).json()) == 1


def test_quem_nunca_enviou_comprovante_pode_enviar(client, fila):
    # Conta criada por um gestor: ativa e sem comprovante
    usuario = fila.usuario_no_banco()

    resposta = client.post(
        "/comprovantes", json={"arquivo_url": LINK}, headers=com_token(usuario["id"])
    )

    assert resposta.status_code == 201


@pytest.mark.parametrize(
    "link",
    [
        "http://res.cloudinary.com/demo/c.pdf",
        "https://res.cloudinary.com/demo/c.docx",
        "https://res.cloudinary.com/demo/c",
        "nao-e-um-link",
        "",
    ],
)
def test_reenvio_valida_o_link_como_no_cadastro(client, fila, link):
    usuario, comprovante = fila.enviar()
    fila.decidir(client, comprovante, "recusar", motivo_recusa="Ilegível")

    resposta = client.post(
        "/comprovantes", json={"arquivo_url": link}, headers=com_token(usuario["id"])
    )

    assert resposta.status_code == 422


def test_rotas_do_proprio_comprovante_exigem_login(client, fila):
    assert client.get("/comprovantes/meus").status_code == 401
    assert client.post("/comprovantes", json={"arquivo_url": LINK}).status_code == 401


def test_cada_um_ve_so_os_seus_comprovantes(client, fila):
    dono, _ = fila.enviar()
    outro, _ = fila.enviar()

    meus = client.get("/comprovantes/meus", headers=com_token(dono["id"])).json()

    assert len(meus) == 1
    assert meus[0]["usuario_id"] == str(dono["id"])
    assert str(outro["id"]) not in str(meus)
