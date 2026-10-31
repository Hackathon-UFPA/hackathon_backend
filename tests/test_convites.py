"""
Convites, aceite de participação e aceite de termos (RF18, RF19, RF20; BE-S4-04).

Estes testes gravam no banco de verdade; a fixture `cenario` apaga tudo o que cria.
"""

from uuid import uuid4

import pytest

from app.security.token import criar_token

SENHA = "segredo123"


def com_token(usuario_id) -> dict:
    return {"Authorization": f"Bearer {criar_token(usuario_id)}"}


class Cenario:
    """Hackathon em inscrições, termos vigentes, uma equipe e o seu líder."""

    def __init__(self, sql, usuario_no_banco, novo_email):
        self.sql = sql
        self.usuario_no_banco = usuario_no_banco
        self.novo_email = novo_email
        self.hackathons: list = []

        self.hackathon_id = self.criar_hackathon()
        self.termo_regulamento = self.criar_termo(self.hackathon_id, "REGULAMENTO")
        self.termo_consentimento = self.criar_termo(self.hackathon_id, "TERMO_CONSENTIMENTO")
        self.lider = usuario_no_banco()
        self.equipe_id = self.criar_equipe(self.hackathon_id, self.lider)

    @property
    def termos_ids(self) -> list[str]:
        return [str(self.termo_regulamento), str(self.termo_consentimento)]

    def criar_hackathon(self, **campos):
        id_ = self.sql(
            "INSERT INTO hackathon (nome, status, data_inicio) VALUES"
            " ('Teste de convites', 'INSCRICOES', '2098-01-01') RETURNING id"
        )[0]["id"]
        self.hackathons.append(id_)
        return id_

    def criar_termo(self, hackathon_id, tipo: str, versao: str = "1.0", vigente: bool = True):
        return self.sql(
            "INSERT INTO termos (hackathon_id, tipo, versao, titulo, conteudo, vigente)"
            " VALUES (:h, CAST(:tipo AS tipo_termo), :versao, 'Documento', 'Texto', :vigente)"
            " RETURNING id",
            h=hackathon_id,
            tipo=tipo,
            versao=versao,
            vigente=vigente,
        )[0]["id"]

    def criar_equipe(self, hackathon_id, lider: dict):
        equipe_id = self.sql(
            "INSERT INTO equipes (hackathon_id, nome) VALUES (:h, 'Equipe de teste') RETURNING id",
            h=hackathon_id,
        )[0]["id"]
        self.sql(
            "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id, funcao)"
            " VALUES (:e, :u, :h, 'LIDER')",
            e=equipe_id,
            u=lider["id"],
            h=hackathon_id,
        )
        return equipe_id

    def definir_status(self, status: str):
        self.sql(
            "UPDATE hackathon SET status = CAST(:s AS status_hackathon) WHERE id = :id",
            s=status,
            id=self.hackathon_id,
        )

    def definir_maximo(self, maximo: int):
        self.sql(
            "UPDATE hackathon SET max_integrantes = :m,"
            " min_integrantes = LEAST(min_integrantes, :m) WHERE id = :id",
            m=maximo,
            id=self.hackathon_id,
        )

    def trocar_termo_vigente(self, tipo: str, versao: str):
        self.sql(
            "UPDATE termos SET vigente = false"
            " WHERE hackathon_id = :h AND tipo = CAST(:t AS tipo_termo)",
            h=self.hackathon_id,
            t=tipo,
        )
        return self.criar_termo(self.hackathon_id, tipo, versao=versao)

    def convidar(self, client, email: str | None = None, nome: str = "Maria Souza", quem=None):
        return client.post(
            f"/equipes/{self.equipe_id}/convites",
            json={"nome": nome, "email": email or self.novo_email()},
            headers=com_token((quem or self.lider)["id"]),
        )

    def convidar_usuario(self, client) -> tuple[dict, str]:
        """Cria um usuário e um convite pendente dirigido ao e-mail dele."""
        convidado = self.usuario_no_banco()
        resposta = self.convidar(client, email=convidado["email"])
        assert resposta.status_code == 201, resposta.text
        return convidado, resposta.json()["id"]

    def aceitar(self, client, convidado: dict, convite_id: str, termos_ids=None):
        return client.post(
            f"/convites/{convite_id}/aceitar",
            json={"termos_ids": self.termos_ids if termos_ids is None else termos_ids},
            headers=com_token(convidado["id"]),
        )

    def recusar(self, client, convidado: dict, convite_id: str):
        return client.post(f"/convites/{convite_id}/recusar", headers=com_token(convidado["id"]))

    def limpar(self):
        for h in self.hackathons:
            self.sql(
                "DELETE FROM convites WHERE equipe_id IN (SELECT id FROM equipes"
                " WHERE hackathon_id = :h)",
                h=h,
            )
            self.sql(
                "DELETE FROM aceites_termos WHERE termo_id IN (SELECT id FROM termos"
                " WHERE hackathon_id = :h)",
                h=h,
            )
            self.sql("DELETE FROM membros_equipe WHERE hackathon_id = :h", h=h)
            self.sql("DELETE FROM equipes WHERE hackathon_id = :h", h=h)
            self.sql("DELETE FROM termos WHERE hackathon_id = :h", h=h)
            self.sql("DELETE FROM hackathon WHERE id = :h", h=h)


@pytest.fixture
def cenario(sql, usuario_no_banco, novo_email):
    # Depende de usuario_no_banco: este teardown roda antes de apagar os usuários
    c = Cenario(sql, usuario_no_banco, novo_email)
    yield c
    c.limpar()


@pytest.mark.parametrize("operacao", ["enviar", "aceitar", "recusar"])
def test_convites_respeitam_periodo_do_edital(client, cenario, sql, periodo_inscricoes, operacao):
    convidado = cenario.usuario_no_banco()
    if operacao != "enviar":
        convite = cenario.convidar(client, email=convidado["email"])
        assert convite.status_code == 201, convite.text
        convite_id = convite.json()["id"]
    permitido = periodo_inscricoes(cenario.hackathon_id)

    if operacao == "enviar":
        resposta = cenario.convidar(client, email=convidado["email"])
    else:
        resposta = getattr(cenario, operacao)(client, convidado, convite_id)

    assert resposta.status_code == ((201 if operacao == "enviar" else 200) if permitido else 409)
    if not permitido:
        assert resposta.json() == {"detail": "As inscrições deste hackathon não estão abertas."}
    convites = sql("SELECT status FROM convites WHERE equipe_id = :e", e=cenario.equipe_id)
    esperado = {"enviar": "PENDENTE", "aceitar": "ACEITO", "recusar": "RECUSADO"}[operacao]
    assert [c["status"] for c in convites] == (
        [esperado] if permitido else ([] if operacao == "enviar" else ["PENDENTE"])
    )
    membros = sql(
        "SELECT * FROM membros_equipe WHERE equipe_id = :e AND usuario_id = :u",
        e=cenario.equipe_id,
        u=convidado["id"],
    )
    aceites = sql("SELECT * FROM aceites_termos WHERE usuario_id = :u", u=convidado["id"])
    assert len(membros) == (1 if permitido and operacao == "aceitar" else 0)
    assert len(aceites) == (2 if permitido and operacao == "aceitar" else 0)


def test_cancelamento_continua_permitido_apos_prazo(client, cenario, sql):
    _, convite_id = cenario.convidar_usuario(client)
    sql(
        "UPDATE hackathon SET inscricoes_fim = now() - interval '1 day' WHERE id = :h",
        h=cenario.hackathon_id,
    )
    sql("UPDATE equipes SET situacao = 'HOMOLOGADA' WHERE id = :e", e=cenario.equipe_id)

    resposta = client.post(
        f"/convites/{convite_id}/cancelar", headers=com_token(cenario.lider["id"])
    )

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "CANCELADO"


def test_aceite_de_termos_continua_permitido_apos_prazo(client, cenario, sql):
    sql(
        "UPDATE hackathon SET inscricoes_fim = now() - interval '1 day' WHERE id = :h",
        h=cenario.hackathon_id,
    )

    resposta = client.post(
        f"/hackathons/{cenario.hackathon_id}/termos/aceites",
        json={"termos_ids": cenario.termos_ids},
        headers=com_token(cenario.lider["id"]),
    )

    assert resposta.status_code == 201
    assert sorted(a["termo_id"] for a in resposta.json()) == sorted(cenario.termos_ids)


# --- Enviar convite (RF18) ---


def test_lider_convida_por_nome_e_email(client, cenario):
    resposta = cenario.convidar(client, email="Maria.Souza@Testes.com")

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "PENDENTE"
    assert corpo["email"] == "maria.souza@testes.com"
    assert corpo["equipe_id"] == str(cenario.equipe_id)
    assert corpo["convidado_por"] == str(cenario.lider["id"])
    assert "token" not in corpo


def test_convite_a_quem_ja_tem_conta_guarda_o_usuario(client, cenario, sql):
    convidado = cenario.usuario_no_banco()

    resposta = cenario.convidar(client, email=convidado["email"].upper())

    assert resposta.status_code == 201
    assert resposta.json()["usuario_id"] == str(convidado["id"])


def test_sem_token_nao_convida(client, cenario):
    resposta = client.post(
        f"/equipes/{cenario.equipe_id}/convites", json={"nome": "A", "email": "a@testes.com"}
    )

    assert resposta.status_code == 401


def test_quem_nao_e_da_equipe_nao_convida(client, cenario):
    de_fora = cenario.usuario_no_banco()

    assert cenario.convidar(client, quem=de_fora).status_code == 403


def test_integrante_que_nao_e_lider_nao_convida(client, cenario, sql):
    membro, convite_id = cenario.convidar_usuario(client)
    assert cenario.aceitar(client, membro, convite_id).status_code == 200

    assert cenario.convidar(client, quem=membro).status_code == 403


def test_conta_pendente_nao_convida(client, cenario, sql):
    cenario.sql(
        "UPDATE usuarios SET situacao_conta = 'PENDENTE' WHERE id = :id", id=cenario.lider["id"]
    )

    assert cenario.convidar(client).status_code == 403


def test_equipe_inexistente(client, cenario):
    resposta = client.post(
        f"/equipes/{uuid4()}/convites",
        json={"nome": "A", "email": "a@testes.com"},
        headers=com_token(cenario.lider["id"]),
    )

    assert resposta.status_code == 404


def test_email_invalido_e_nome_vazio(client, cenario):
    cabecalho = com_token(cenario.lider["id"])
    url = f"/equipes/{cenario.equipe_id}/convites"

    assert (
        client.post(url, json={"nome": "A", "email": "sem-arroba"}, headers=cabecalho).status_code
        == 422
    )
    assert (
        client.post(
            url, json={"nome": "  ", "email": "a@testes.com"}, headers=cabecalho
        ).status_code
        == 422
    )


def test_convite_repetido_para_o_mesmo_email(client, cenario):
    email = cenario.novo_email()
    assert cenario.convidar(client, email=email).status_code == 201

    assert cenario.convidar(client, email=email.upper()).status_code == 409


def test_nao_convida_quem_ja_e_integrante(client, cenario):
    assert cenario.convidar(client, email=cenario.lider["email"]).status_code == 409


def test_respeita_o_maximo_de_integrantes_contando_pendentes(client, cenario):
    cenario.definir_maximo(3)  # o líder já ocupa uma vaga
    assert cenario.convidar(client).status_code == 201
    assert cenario.convidar(client).status_code == 201

    assert cenario.convidar(client).status_code == 409


def test_nao_convida_fora_do_periodo_de_inscricoes(client, cenario):
    cenario.definir_status("INSCRICOES_ENCERRADAS")

    assert cenario.convidar(client).status_code == 409


# --- Listagens ---


def test_equipe_lista_os_convites_com_o_estado(client, cenario):
    recusou, convite_recusado = cenario.convidar_usuario(client)
    cenario.convidar_usuario(client)
    assert cenario.recusar(client, recusou, convite_recusado).status_code == 200

    resposta = client.get(
        f"/equipes/{cenario.equipe_id}/convites", headers=com_token(cenario.lider["id"])
    )

    assert resposta.status_code == 200
    estados = sorted(convite["status"] for convite in resposta.json())
    assert estados == ["PENDENTE", "RECUSADO"]


def test_quem_nao_e_da_equipe_nao_ve_os_convites(client, cenario):
    de_fora = cenario.usuario_no_banco()

    resposta = client.get(
        f"/equipes/{cenario.equipe_id}/convites", headers=com_token(de_fora["id"])
    )

    assert resposta.status_code == 403


def test_convidado_ve_o_convite_no_painel(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    outra_pessoa = cenario.usuario_no_banco()

    meus = client.get("/convites/meus", headers=com_token(convidado["id"]))
    dela = client.get("/convites/meus", headers=com_token(outra_pessoa["id"]))

    assert meus.status_code == 200
    assert [c["id"] for c in meus.json()] == [convite_id]
    assert meus.json()[0]["equipe_nome"] == "Equipe de teste"
    assert meus.json()[0]["hackathon_id"] == str(cenario.hackathon_id)
    assert dela.json() == []


def test_convite_respondido_sai_do_painel(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    assert cenario.recusar(client, convidado, convite_id).status_code == 200

    assert client.get("/convites/meus", headers=com_token(convidado["id"])).json() == []


# --- Aceitar (RF19, RF20, RN02, RN05, RN06) ---


def test_aceitar_entra_na_equipe_e_registra_os_termos(client, cenario, sql):
    convidado, convite_id = cenario.convidar_usuario(client)

    resposta = cenario.aceitar(client, convidado, convite_id)

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ACEITO"
    assert resposta.json()["usuario_id"] == str(convidado["id"])
    assert resposta.json()["respondido_em"] is not None

    membro = sql(
        "SELECT hackathon_id FROM membros_equipe WHERE equipe_id = :e AND usuario_id = :u",
        e=cenario.equipe_id,
        u=convidado["id"],
    )
    assert [m["hackathon_id"] for m in membro] == [cenario.hackathon_id]

    aceites = sql(
        "SELECT t.tipo::text AS tipo, t.versao, a.aceito_em FROM aceites_termos a"
        " JOIN termos t ON t.id = a.termo_id WHERE a.usuario_id = :u ORDER BY t.tipo",
        u=convidado["id"],
    )
    assert [(a["tipo"], a["versao"]) for a in aceites] == [
        ("REGULAMENTO", "1.0"),
        ("TERMO_CONSENTIMENTO", "1.0"),
    ]
    assert all(a["aceito_em"] is not None for a in aceites)


def test_aceitar_mantem_a_versao_dos_termos_aceita(client, cenario, sql):
    convidado, convite_id = cenario.convidar_usuario(client)
    assert cenario.aceitar(client, convidado, convite_id).status_code == 200

    cenario.trocar_termo_vigente("REGULAMENTO", "2.0")

    versoes = sql(
        "SELECT t.versao FROM aceites_termos a JOIN termos t ON t.id = a.termo_id"
        " WHERE a.usuario_id = :u AND t.tipo = 'REGULAMENTO'",
        u=convidado["id"],
    )
    assert [v["versao"] for v in versoes] == ["1.0"]


def test_aceitar_duas_vezes(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    assert cenario.aceitar(client, convidado, convite_id).status_code == 200

    assert cenario.aceitar(client, convidado, convite_id).status_code == 409


def test_aceitar_exige_os_dois_termos(client, cenario, sql):
    convidado, convite_id = cenario.convidar_usuario(client)

    resposta = cenario.aceitar(client, convidado, convite_id, termos_ids=cenario.termos_ids[:1])

    assert resposta.status_code == 422
    assert sql("SELECT 1 FROM membros_equipe WHERE usuario_id = :u", u=convidado["id"]) == []
    assert sql("SELECT 1 FROM aceites_termos WHERE usuario_id = :u", u=convidado["id"]) == []


def test_aceitar_sem_enviar_termos(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)

    assert cenario.aceitar(client, convidado, convite_id, termos_ids=[]).status_code == 422


def test_aceitar_versao_que_deixou_de_ser_vigente(client, cenario, sql):
    convidado, convite_id = cenario.convidar_usuario(client)
    cenario.trocar_termo_vigente("REGULAMENTO", "2.0")

    resposta = cenario.aceitar(client, convidado, convite_id)

    assert resposta.status_code == 409
    assert sql("SELECT 1 FROM membros_equipe WHERE usuario_id = :u", u=convidado["id"]) == []


def test_aceitar_sem_termos_publicados(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    cenario.sql("UPDATE termos SET vigente = false WHERE hackathon_id = :h", h=cenario.hackathon_id)

    assert cenario.aceitar(client, convidado, convite_id).status_code == 409


def test_nao_aceita_quem_ja_esta_em_outra_equipe(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    outro_lider = cenario.usuario_no_banco()
    outra_equipe = cenario.criar_equipe(cenario.hackathon_id, outro_lider)
    cenario.sql(
        "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id) VALUES (:e, :u, :h)",
        e=outra_equipe,
        u=convidado["id"],
        h=cenario.hackathon_id,
    )

    assert cenario.aceitar(client, convidado, convite_id).status_code == 409


def test_pode_aceitar_quem_esta_em_equipe_de_outro_hackathon(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    outro_hackathon = cenario.criar_hackathon()
    outro_lider = cenario.usuario_no_banco()
    outra_equipe = cenario.criar_equipe(outro_hackathon, outro_lider)
    cenario.sql(
        "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id) VALUES (:e, :u, :h)",
        e=outra_equipe,
        u=convidado["id"],
        h=outro_hackathon,
    )

    assert cenario.aceitar(client, convidado, convite_id).status_code == 200


def test_nao_aceita_com_a_equipe_cheia(client, cenario):
    cenario.definir_maximo(3)  # o líder e mais dois
    primeiro, convite_1 = cenario.convidar_usuario(client)
    segundo, convite_2 = cenario.convidar_usuario(client)
    assert cenario.aceitar(client, primeiro, convite_1).status_code == 200
    assert cenario.aceitar(client, segundo, convite_2).status_code == 200
    # Convite pendente que sobrou (ex.: o limite foi reduzido depois de enviado)
    ultimo = cenario.usuario_no_banco()
    convite = cenario.sql(
        "INSERT INTO convites (equipe_id, nome, email, convidado_por)"
        " VALUES (:e, 'Fulano', :email, :l) RETURNING id",
        e=cenario.equipe_id,
        email=ultimo["email"],
        l=cenario.lider["id"],
    )[0]["id"]

    assert cenario.aceitar(client, ultimo, str(convite)).status_code == 409


def test_nao_aceita_fora_do_periodo_de_inscricoes(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    cenario.definir_status("INSCRICOES_ENCERRADAS")

    assert cenario.aceitar(client, convidado, convite_id).status_code == 409


def test_so_o_destinatario_responde(client, cenario):
    _, convite_id = cenario.convidar_usuario(client)
    intruso = cenario.usuario_no_banco()

    assert cenario.aceitar(client, intruso, convite_id).status_code == 404
    assert cenario.recusar(client, intruso, convite_id).status_code == 404


def test_convite_inexistente(client, cenario):
    assert cenario.recusar(client, cenario.lider, str(uuid4())).status_code == 404


def test_responder_exige_login(client, cenario):
    _, convite_id = cenario.convidar_usuario(client)

    resposta = client.post(f"/convites/{convite_id}/recusar")

    assert resposta.status_code == 401


# --- Recusar (RF19) ---


def test_recusar_libera_a_vaga_e_o_lider_ve(client, cenario):
    cenario.definir_maximo(2)  # líder + 1 vaga
    convidado, convite_id = cenario.convidar_usuario(client)
    assert cenario.convidar(client).status_code == 409  # sem vaga

    resposta = cenario.recusar(client, convidado, convite_id)

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "RECUSADO"
    assert resposta.json()["respondido_em"] is not None
    assert cenario.convidar(client).status_code == 201  # a vaga ficou livre


def test_pode_convidar_de_novo_quem_recusou(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    assert cenario.recusar(client, convidado, convite_id).status_code == 200

    assert cenario.convidar(client, email=convidado["email"]).status_code == 201


def test_recusar_duas_vezes(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    assert cenario.recusar(client, convidado, convite_id).status_code == 200

    assert cenario.recusar(client, convidado, convite_id).status_code == 409


def test_nao_recusa_fora_do_periodo_de_inscricoes(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    cenario.definir_status("INSCRICOES_ENCERRADAS")

    assert cenario.recusar(client, convidado, convite_id).status_code == 409


# --- Cancelar ---


def test_lider_cancela_convite_pendente(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)

    resposta = client.post(
        f"/convites/{convite_id}/cancelar", headers=com_token(cenario.lider["id"])
    )

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "CANCELADO"
    assert cenario.aceitar(client, convidado, convite_id).status_code == 409


def test_so_o_lider_cancela(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)

    resposta = client.post(f"/convites/{convite_id}/cancelar", headers=com_token(convidado["id"]))

    assert resposta.status_code == 403


def test_nao_cancela_convite_ja_aceito(client, cenario):
    convidado, convite_id = cenario.convidar_usuario(client)
    assert cenario.aceitar(client, convidado, convite_id).status_code == 200

    resposta = client.post(
        f"/convites/{convite_id}/cancelar", headers=com_token(cenario.lider["id"])
    )

    assert resposta.status_code == 409


# --- Termos (RF20) ---


def test_termos_vigentes_para_ler_antes_de_aceitar(client, cenario):
    cenario.criar_termo(cenario.hackathon_id, "REGULAMENTO", versao="0.9", vigente=False)

    resposta = client.get(
        f"/hackathons/{cenario.hackathon_id}/termos/vigentes",
        headers=com_token(cenario.lider["id"]),
    )

    assert resposta.status_code == 200
    ids = sorted(termo["id"] for termo in resposta.json())
    assert ids == sorted(cenario.termos_ids)
    assert {termo["versao"] for termo in resposta.json()} == {"1.0"}


def test_termos_de_hackathon_inexistente(client, cenario):
    resposta = client.get(
        f"/hackathons/{uuid4()}/termos/vigentes", headers=com_token(cenario.lider["id"])
    )

    assert resposta.status_code == 404


def test_aceitar_termos_registra_data_e_versao(client, cenario):
    resposta = client.post(
        f"/hackathons/{cenario.hackathon_id}/termos/aceites",
        json={"termos_ids": cenario.termos_ids},
        headers=com_token(cenario.lider["id"]),
    )

    assert resposta.status_code == 201
    assert sorted(a["termo_id"] for a in resposta.json()) == sorted(cenario.termos_ids)
    assert all(a["aceito_em"] for a in resposta.json())
    assert all(a["usuario_id"] == str(cenario.lider["id"]) for a in resposta.json())


def test_aceitar_termos_de_novo_nao_duplica(client, cenario, sql):
    url = f"/hackathons/{cenario.hackathon_id}/termos/aceites"
    cabecalho = com_token(cenario.lider["id"])
    primeiro = client.post(url, json={"termos_ids": cenario.termos_ids}, headers=cabecalho)

    segundo = client.post(url, json={"termos_ids": cenario.termos_ids}, headers=cabecalho)

    assert segundo.status_code == 201
    assert sorted(a["aceito_em"] for a in segundo.json()) == sorted(
        a["aceito_em"] for a in primeiro.json()
    )
    total = sql(
        "SELECT count(*) AS n FROM aceites_termos WHERE usuario_id = :u", u=cenario.lider["id"]
    )
    assert total[0]["n"] == 2


def test_aceitar_termos_exige_os_dois(client, cenario):
    resposta = client.post(
        f"/hackathons/{cenario.hackathon_id}/termos/aceites",
        json={"termos_ids": cenario.termos_ids[:1]},
        headers=com_token(cenario.lider["id"]),
    )

    assert resposta.status_code == 422


def test_aceitar_termos_de_outro_hackathon(client, cenario):
    outro = cenario.criar_hackathon()
    termo_de_outro = cenario.criar_termo(outro, "REGULAMENTO")

    resposta = client.post(
        f"/hackathons/{cenario.hackathon_id}/termos/aceites",
        json={"termos_ids": [str(termo_de_outro), *cenario.termos_ids[1:]]},
        headers=com_token(cenario.lider["id"]),
    )

    assert resposta.status_code == 409
