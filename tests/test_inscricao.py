"""
Conclusão da inscrição, homologação automática e painel da equipe (BE-S4-05: RF22, RF23, RF25).

Os testes percorrem o fluxo de verdade: convite, aceite de termos, conferência de comprovante.
Gravam no banco; a fixture `inscricao` apaga o que criou.
"""

import re
from uuid import uuid4

import pytest

from tests.test_convites import Cenario, com_token
from tests.test_migrations import rodar
from tests.test_migrations import sql as sql_na_transacao


class CenarioInscricao(Cenario):
    def entrar(self, client) -> dict:
        """Cria um usuário, convida e aceita o convite (com os termos vigentes)."""
        usuario, convite_id = self.convidar_usuario(client)
        assert self.aceitar(client, usuario, convite_id).status_code == 200
        return usuario

    def lider_aceita_termos(self, client):
        resposta = client.post(
            f"/hackathons/{self.hackathon_id}/termos/aceites",
            json={"termos_ids": self.termos_ids},
            headers=com_token(self.lider["id"]),
        )
        assert resposta.status_code == 201, resposta.text

    def comprovante(self, usuario: dict, status: str = "APROVADO", motivo: str | None = None):
        validado = "NULL" if status == "PENDENTE" else "now()"
        return self.sql(
            "INSERT INTO comprovantes_vinculo (usuario_id, hackathon_id, arquivo_url, status,"
            f" motivo_recusa, validado_em) VALUES (:u, :h, 'https://x.com/c.pdf',"
            f" CAST(:s AS status_comprovante), :m, {validado}) RETURNING id",
            u=usuario["id"],
            h=self.hackathon_id,
            s=status,
            m=motivo,
        )[0]["id"]

    def montar(self, client, *, integrantes: int = 3, vinculos: bool = False) -> list[dict]:
        """Líder com termos aceitos e mais `integrantes - 1` pessoas na equipe. Com `vinculos`,
        todos já têm o comprovante aprovado."""
        self.lider_aceita_termos(client)
        pessoas = [self.lider] + [self.entrar(client) for _ in range(integrantes - 1)]
        if vinculos:
            for pessoa in pessoas:
                self.comprovante(pessoa)
        return pessoas

    def concluir(self, client, quem=None):
        return client.post(
            f"/equipes/{self.equipe_id}/inscricao/concluir",
            headers=com_token((quem or self.lider)["id"]),
        )

    def painel(self, client, quem=None):
        return client.get(
            f"/equipes/{self.equipe_id}/painel", headers=com_token((quem or self.lider)["id"])
        )

    def equipe(self) -> dict:
        return self.sql(
            "SELECT situacao::text AS situacao, inscricao_concluida_em, homologada_em"
            " FROM equipes WHERE id = :e",
            e=self.equipe_id,
        )[0]

    def protocolos(self) -> list[dict]:
        return self.sql("SELECT * FROM protocolos WHERE equipe_id = :e", e=self.equipe_id)

    def limpar(self):
        for h in self.hackathons:
            self.sql(
                "DELETE FROM protocolos WHERE equipe_id IN"
                " (SELECT id FROM equipes WHERE hackathon_id = :h)",
                h=h,
            )
            self.sql("DELETE FROM comprovantes_vinculo WHERE hackathon_id = :h", h=h)
        super().limpar()


@pytest.fixture
def inscricao(sql, usuario_no_banco, novo_email):
    c = CenarioInscricao(sql, usuario_no_banco, novo_email)
    yield c
    c.limpar()


# --- Concluir a inscrição (RF22) ---


def test_lider_conclui_com_tres_integrantes_e_recebe_a_confirmacao(client, inscricao):
    inscricao.montar(client)

    resposta = inscricao.concluir(client)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["situacao"] == "AGUARDANDO_HOMOLOGACAO"
    assert corpo["homologada_em"] is None
    assert corpo["inscricao_concluida_em"] is not None
    assert re.fullmatch(r"HK\d{4}-\d{6}", corpo["protocolo"]["numero"])
    assert corpo["protocolo"]["numero"] in corpo["mensagem"]
    protocolos = inscricao.protocolos()
    assert len(protocolos) == 1
    assert protocolos[0]["tipo"] == "INSCRICAO_EQUIPE"
    assert protocolos[0]["emitido_por"] == inscricao.lider["id"]
    assert inscricao.equipe()["situacao"] == "AGUARDANDO_HOMOLOGACAO"


@pytest.mark.parametrize("integrantes", [3, 5])
def test_aceita_os_limites_de_tres_e_cinco_integrantes(client, inscricao, integrantes):
    inscricao.montar(client, integrantes=integrantes)
    assert inscricao.concluir(client).status_code == 200


def test_conclusao_homologa_quando_todos_ja_tem_vinculo_aprovado(client, inscricao):
    inscricao.montar(client, vinculos=True)

    corpo = inscricao.concluir(client).json()

    assert corpo["situacao"] == "HOMOLOGADA"
    assert corpo["homologada_em"] is not None
    assert "homologada" in corpo["mensagem"]
    assert inscricao.equipe()["situacao"] == "HOMOLOGADA"


@pytest.mark.parametrize("quem", ["integrante", "de_fora"])
def test_so_o_lider_conclui(client, inscricao, quem):
    pessoas = inscricao.montar(client)
    alvo = pessoas[1] if quem == "integrante" else inscricao.usuario_no_banco()

    assert inscricao.concluir(client, quem=alvo).status_code == 403
    assert inscricao.equipe()["situacao"] == "EM_FORMACAO"
    assert inscricao.protocolos() == []


def test_dev_conclui_pela_excecao_tecnica(client, inscricao):
    inscricao.montar(client)
    dev = inscricao.usuario_no_banco(papel="DEV")

    assert inscricao.concluir(client, quem=dev).status_code == 200


def test_sem_token_e_equipe_inexistente(client, inscricao):
    assert client.post(f"/equipes/{inscricao.equipe_id}/inscricao/concluir").status_code == 401
    resposta = client.post(
        f"/equipes/{uuid4()}/inscricao/concluir", headers=com_token(inscricao.lider["id"])
    )
    assert resposta.status_code == 404


def test_conta_pendente_do_lider_nao_conclui(client, inscricao):
    inscricao.montar(client)
    inscricao.sql(
        "UPDATE usuarios SET situacao_conta = 'PENDENTE' WHERE id = :u", u=inscricao.lider["id"]
    )

    assert inscricao.concluir(client).status_code == 403


def test_exige_o_minimo_de_integrantes(client, inscricao):
    inscricao.montar(client, integrantes=2)

    resposta = inscricao.concluir(client)

    assert resposta.status_code == 409
    assert "pelo menos 3" in resposta.json()["detail"]
    assert inscricao.equipe()["situacao"] == "EM_FORMACAO"
    assert inscricao.protocolos() == []


def test_exige_o_maximo_de_integrantes(client, inscricao):
    inscricao.montar(client, integrantes=3)
    inscricao.definir_maximo(2)

    resposta = inscricao.concluir(client)

    assert resposta.status_code == 409
    assert "máximo é 2" in resposta.json()["detail"]


def test_o_tamanho_vem_do_hackathon(client, inscricao):
    inscricao.montar(client, integrantes=2)
    inscricao.sql(
        "UPDATE hackathon SET min_integrantes = 2 WHERE id = :h", h=inscricao.hackathon_id
    )

    assert inscricao.concluir(client).status_code == 200


def test_o_lider_tambem_precisa_ter_aceitado_os_termos(client, inscricao):
    for _ in range(2):
        inscricao.entrar(client)

    resposta = inscricao.concluir(client)

    assert resposta.status_code == 409
    assert "aceitar o regulamento" in resposta.json()["detail"]
    inscricao.lider_aceita_termos(client)
    assert inscricao.concluir(client).status_code == 200


def test_termos_desatualizados_de_um_integrante_bloqueiam(client, inscricao):
    inscricao.montar(client)
    inscricao.trocar_termo_vigente("REGULAMENTO", "2.0")

    resposta = inscricao.concluir(client)

    assert resposta.status_code == 409
    assert "termos" in resposta.json()["detail"] or "regulamento" in resposta.json()["detail"]


def test_sem_termos_publicados_nao_conclui(client, inscricao):
    inscricao.montar(client)
    inscricao.sql(
        "UPDATE termos SET vigente = false WHERE hackathon_id = :h", h=inscricao.hackathon_id
    )

    resposta = inscricao.concluir(client)

    assert resposta.status_code == 409
    assert "ainda não foram publicados" in resposta.json()["detail"]


def test_conta_desativada_de_integrante_bloqueia(client, inscricao):
    pessoas = inscricao.montar(client)
    inscricao.sql("UPDATE usuarios SET ativo = false WHERE id = :u", u=pessoas[2]["id"])

    resposta = inscricao.concluir(client)

    assert resposta.status_code == 409
    assert "desativada" in resposta.json()["detail"]


def test_fora_do_prazo_pelo_status(client, inscricao):
    inscricao.montar(client)
    inscricao.definir_status("INSCRICOES_ENCERRADAS")

    assert inscricao.concluir(client).status_code == 409
    assert inscricao.equipe()["situacao"] == "EM_FORMACAO"


def test_fora_do_prazo_pelas_datas_do_edital(client, inscricao):
    inscricao.montar(client)
    inscricao.sql(
        "UPDATE hackathon SET inscricoes_inicio = now() - interval '10 days',"
        " inscricoes_fim = now() - interval '1 day' WHERE id = :h",
        h=inscricao.hackathon_id,
    )

    assert inscricao.concluir(client).status_code == 409


def test_dentro_das_datas_do_edital(client, inscricao):
    inscricao.montar(client)
    inscricao.sql(
        "UPDATE hackathon SET inscricoes_inicio = now() - interval '1 day',"
        " inscricoes_fim = now() + interval '1 day' WHERE id = :h",
        h=inscricao.hackathon_id,
    )

    assert inscricao.concluir(client).status_code == 200


def test_nao_conclui_duas_vezes(client, inscricao):
    inscricao.montar(client)
    assert inscricao.concluir(client).status_code == 200

    segunda = inscricao.concluir(client)

    assert segunda.status_code == 409
    assert "já foi concluída" in segunda.json()["detail"]
    assert len(inscricao.protocolos()) == 1


def test_conclusao_fecha_a_composicao_e_cancela_convites_em_aberto(client, inscricao):
    inscricao.montar(client)
    pendente, convite_id = inscricao.convidar_usuario(client)

    assert inscricao.concluir(client).status_code == 200

    status_do_convite = inscricao.sql(
        "SELECT status::text AS s FROM convites WHERE id = :c", c=convite_id
    )
    assert status_do_convite[0]["s"] == "CANCELADO"
    assert inscricao.convidar(client).status_code == 409
    assert inscricao.aceitar(client, pendente, convite_id).status_code == 409


# --- Homologação automática e reversão (RF23) ---


def test_aprovar_o_ultimo_comprovante_homologa_a_equipe(client, inscricao):
    pessoas = inscricao.montar(client)
    for pessoa in pessoas:
        inscricao.comprovante(pessoa, "PENDENTE")
    assert inscricao.concluir(client).json()["situacao"] == "AGUARDANDO_HOMOLOGACAO"
    organizador = inscricao.usuario_no_banco(papel="ORGANIZADOR")
    ids = [
        linha["id"]
        for linha in inscricao.sql(
            "SELECT id FROM comprovantes_vinculo WHERE hackathon_id = :h", h=inscricao.hackathon_id
        )
    ]

    for indice, comprovante_id in enumerate(ids):
        resposta = client.post(
            f"/admin/comprovantes/{comprovante_id}/aprovar", headers=com_token(organizador["id"])
        )
        assert resposta.status_code == 200, resposta.text
        esperado = "HOMOLOGADA" if indice == len(ids) - 1 else "AGUARDANDO_HOMOLOGACAO"
        assert inscricao.equipe()["situacao"] == esperado

    assert inscricao.equipe()["homologada_em"] is not None


def test_recusar_um_comprovante_nao_homologa(client, inscricao):
    pessoas = inscricao.montar(client)
    for pessoa in pessoas[:2]:
        inscricao.comprovante(pessoa)
    ultimo = inscricao.comprovante(pessoas[2], "PENDENTE")
    inscricao.concluir(client)
    organizador = inscricao.usuario_no_banco(papel="ORGANIZADOR")

    resposta = client.post(
        f"/admin/comprovantes/{ultimo}/recusar",
        json={"motivo_recusa": "Documento ilegível"},
        headers=com_token(organizador["id"]),
    )

    assert resposta.status_code == 200
    assert inscricao.equipe()["situacao"] == "AGUARDANDO_HOMOLOGACAO"


def test_homologacao_volta_a_pendente_e_retorna_quando_os_requisitos_voltam(client, inscricao):
    pessoas = inscricao.montar(client, vinculos=True)
    assert inscricao.concluir(client).json()["situacao"] == "HOMOLOGADA"
    organizador = inscricao.usuario_no_banco(papel="ORGANIZADOR")
    cabecalho = com_token(organizador["id"])
    url = f"/admin/hackathons/{inscricao.hackathon_id}/equipes/reavaliar"

    # Nada mudou: nada muda
    assert client.post(url, headers=cabecalho).json() == {
        "avaliadas": 1,
        "homologadas": 0,
        "revertidas": 0,
    }
    assert inscricao.equipe()["situacao"] == "HOMOLOGADA"

    # Uma nova versão dos termos deixa todos sem o aceite vigente
    regulamento = inscricao.trocar_termo_vigente("REGULAMENTO", "2.0")
    resposta = client.post(url, headers=cabecalho)
    assert resposta.json() == {"avaliadas": 1, "homologadas": 0, "revertidas": 1}
    assert inscricao.equipe()["situacao"] == "AGUARDANDO_HOMOLOGACAO"
    assert inscricao.equipe()["homologada_em"] is None
    # A inscrição concluída continua valendo
    assert inscricao.equipe()["inscricao_concluida_em"] is not None
    assert len(inscricao.protocolos()) == 1

    # Todos aceitam a versão nova e a equipe volta a ser homologada
    ids = [str(regulamento), str(inscricao.termo_consentimento)]
    for pessoa in pessoas:
        aceite = client.post(
            f"/hackathons/{inscricao.hackathon_id}/termos/aceites",
            json={"termos_ids": ids},
            headers=com_token(pessoa["id"]),
        )
        assert aceite.status_code == 201, aceite.text
    assert client.post(url, headers=cabecalho).json() == {
        "avaliadas": 1,
        "homologadas": 1,
        "revertidas": 0,
    }
    assert inscricao.equipe()["situacao"] == "HOMOLOGADA"


def test_reavaliacao_ignora_equipes_em_formacao_e_nao_homologadas(client, inscricao):
    inscricao.montar(client, vinculos=True)
    organizador = inscricao.usuario_no_banco(papel="ORGANIZADOR")

    resposta = client.post(
        f"/admin/hackathons/{inscricao.hackathon_id}/equipes/reavaliar",
        headers=com_token(organizador["id"]),
    )

    assert resposta.json() == {"avaliadas": 0, "homologadas": 0, "revertidas": 0}
    assert inscricao.equipe()["situacao"] == "EM_FORMACAO"


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "COMITE_CIENTIFICO", "MENTOR"])
def test_so_o_organizador_reavalia(client, inscricao, papel):
    usuario = inscricao.usuario_no_banco(papel=papel)
    url = f"/admin/hackathons/{inscricao.hackathon_id}/equipes/reavaliar"

    assert client.post(url, headers=com_token(usuario["id"])).status_code == 403
    assert client.post(url).status_code == 401


def test_reavaliar_hackathon_inexistente(client, inscricao):
    organizador = inscricao.usuario_no_banco(papel="ORGANIZADOR")

    resposta = client.post(
        f"/admin/hackathons/{uuid4()}/equipes/reavaliar", headers=com_token(organizador["id"])
    )

    assert resposta.status_code == 404


# --- Painel da equipe (RF25) ---


def test_painel_mostra_cada_integrante_e_o_que_falta(client, inscricao):
    inscricao.lider_aceita_termos(client)
    aprovado = inscricao.entrar(client)
    sem_comprovante = inscricao.entrar(client)
    inscricao.comprovante(inscricao.lider, "PENDENTE")
    inscricao.comprovante(aprovado)
    em_aberto, _ = inscricao.convidar_usuario(client)
    # `sem_comprovante` nunca enviou nada; um e-mail sem conta também foi convidado
    inscricao.convidar(client, email=inscricao.novo_email(), nome="Sem Conta")

    resposta = inscricao.painel(client)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["situacao"] == "EM_FORMACAO"
    assert corpo["minimo_integrantes"] == 3
    assert corpo["maximo_integrantes"] == 5
    assert corpo["total_integrantes"] == 3
    assert corpo["inscricoes_abertas"] is True
    assert corpo["voce_e_lider"] is True
    assert corpo["pode_concluir"] is True
    assert corpo["protocolo"] is None

    por_usuario = {i["usuario_id"]: i for i in corpo["integrantes"] if i["integrante"]}
    lider = por_usuario[str(inscricao.lider["id"])]
    assert (lider["funcao"], lider["convite"], lider["termos_aceitos"], lider["comprovante"]) == (
        "LIDER",
        None,
        True,
        "PENDENTE",
    )
    membro = por_usuario[str(aprovado["id"])]
    assert (membro["convite"], membro["termos_aceitos"], membro["comprovante"]) == (
        "ACEITO",
        True,
        "APROVADO",
    )
    assert por_usuario[str(sem_comprovante["id"])]["comprovante"] is None
    convites = [i for i in corpo["integrantes"] if not i["integrante"]]
    assert {c["convite"] for c in convites} == {"PENDENTE"}
    assert len(convites) == 2

    codigos = {(p["codigo"], p["usuario_id"]) for p in corpo["pendencias"]}
    assert codigos == {
        ("COMPROVANTE_PENDENTE", str(inscricao.lider["id"])),
        ("COMPROVANTE_NAO_ENVIADO", str(sem_comprovante["id"])),
    }
    # O comprovante pesa só na homologação: a conclusão continua liberada
    assert all(p["bloqueia_conclusao"] is False for p in corpo["pendencias"])
    assert em_aberto["id"] not in por_usuario


def test_painel_lista_o_que_impede_a_conclusao(client, inscricao):
    inscricao.entrar(client)

    corpo = inscricao.painel(client).json()

    bloqueios = {p["codigo"] for p in corpo["pendencias"] if p["bloqueia_conclusao"]}
    assert bloqueios == {"EQUIPE_ABAIXO_DO_MINIMO", "TERMOS_NAO_ACEITOS"}
    assert corpo["pode_concluir"] is False


def test_painel_depois_da_conclusao_traz_o_protocolo(client, inscricao):
    inscricao.montar(client)
    numero = inscricao.concluir(client).json()["protocolo"]["numero"]

    corpo = inscricao.painel(client).json()

    assert corpo["situacao"] == "AGUARDANDO_HOMOLOGACAO"
    assert corpo["protocolo"]["numero"] == numero
    assert corpo["inscricao_concluida_em"] is not None
    assert corpo["pode_concluir"] is False
    assert {p["codigo"] for p in corpo["pendencias"]} == {"COMPROVANTE_NAO_ENVIADO"}


def test_painel_da_equipe_homologada_nao_tem_pendencias(client, inscricao):
    inscricao.montar(client, vinculos=True)
    inscricao.concluir(client)

    corpo = inscricao.painel(client).json()

    assert corpo["situacao"] == "HOMOLOGADA"
    assert corpo["pendencias"] == []
    assert corpo["homologada_em"] is not None


def test_so_o_lider_ve_a_acao_de_concluir(client, inscricao):
    pessoas = inscricao.montar(client)

    assert inscricao.painel(client, quem=pessoas[0]).json()["pode_concluir"] is True
    como_membro = inscricao.painel(client, quem=pessoas[1]).json()
    assert como_membro["voce_e_lider"] is False
    assert como_membro["pode_concluir"] is False


def test_painel_restrito_a_integrantes(client, inscricao):
    de_fora = inscricao.usuario_no_banco()
    dev = inscricao.usuario_no_banco(papel="DEV")

    assert inscricao.painel(client, quem=de_fora).status_code == 403
    assert inscricao.painel(client, quem=dev).status_code == 200
    assert client.get(f"/equipes/{inscricao.equipe_id}/painel").status_code == 401
    inexistente = client.get(f"/equipes/{uuid4()}/painel", headers=com_token(dev["id"]))
    assert inexistente.status_code == 404


def test_painel_nao_expoe_dados_alem_do_necessario(client, inscricao):
    inscricao.montar(client)

    texto = inscricao.painel(client).text

    for segredo in ("senha_hash", "arquivo_url", "token", "motivo_recusa"):
        assert segredo not in texto


# --- Banco ---


def test_banco_barra_segundo_protocolo_de_inscricao_da_mesma_equipe():
    from sqlalchemy.exc import IntegrityError

    async def fn(conn):
        h = await sql_na_transacao(conn, "INSERT INTO hackathon (nome) VALUES ('T') RETURNING id")
        e = await sql_na_transacao(
            conn, "INSERT INTO equipes (hackathon_id) VALUES (:h) RETURNING id", h=h
        )
        for _ in range(2):
            await sql_na_transacao(
                conn,
                "INSERT INTO protocolos (tipo, equipe_id) VALUES ('INSCRICAO_EQUIPE', :e)",
                e=e,
            )

    with pytest.raises(IntegrityError, match="uq_protocolos_inscricao_equipe"):
        rodar(fn)
