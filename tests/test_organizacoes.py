"""Plataforma multi-organização: cada organização só gerencia os próprios hackathons."""

from uuid import uuid4

import pytest

from tests.test_convites import com_token

LINK = "https://res.cloudinary.com/demo/comprovante.pdf"


class DuasOrganizacoes:
    """Organização A (com um hackathon aberto) e organização B, cada uma com Organizador e
    Comitê Científico."""

    def __init__(self, sql, usuario_no_banco):
        self.sql = sql
        self.usuario_no_banco = usuario_no_banco
        self.orgs = [
            sql(
                "INSERT INTO organizacoes (nome, tipo) VALUES (:n, 'EMPRESA') RETURNING id",
                n=f"Org {nome} {uuid4().hex[:6]}",
            )[0]["id"]
            for nome in ("A", "B")
        ]
        self.org_a, self.org_b = self.orgs
        self.org_a_organizador = self.membro("ORGANIZADOR", self.org_a)
        self.org_b_organizador = self.membro("ORGANIZADOR", self.org_b)
        self.org_a_comite = self.membro("COMITE_CIENTIFICO", self.org_a)
        self.org_b_comite = self.membro("COMITE_CIENTIFICO", self.org_b)
        self.hackathon_a = sql(
            "INSERT INTO hackathon (nome, status, organizacao_id)"
            " VALUES ('Hackathon A', 'INSCRICOES', :o) RETURNING id",
            o=self.org_a,
        )[0]["id"]

    def membro(self, papel: str, organizacao_id) -> dict:
        usuario = self.usuario_no_banco(papel=papel)
        self.sql(
            "UPDATE usuarios SET organizacao_id = :o WHERE id = :u",
            o=organizacao_id,
            u=usuario["id"],
        )
        return usuario

    def publicar_termos(self):
        """Regulamento e termo vigentes no hackathon A: o convite de mentor exige os dois."""
        for tipo in ("REGULAMENTO", "TERMO_CONSENTIMENTO"):
            self.sql(
                "INSERT INTO termos (hackathon_id, tipo, versao, titulo, conteudo, vigente)"
                " VALUES (:h, CAST(:t AS tipo_termo), '1.0', 'Termo', 'texto', true)",
                h=self.hackathon_a,
                t=tipo,
            )

    def limpar(self):
        h = self.hackathon_a
        # Mentores e e-mails criados pela API nos testes
        criados = "SELECT id FROM usuarios WHERE organizacao_id = ANY(:o) AND email LIKE 'org_%'"
        self.sql(f"DELETE FROM emails_outbox WHERE usuario_id IN ({criados})", o=self.orgs)
        self.sql(f"DELETE FROM convites_mentor WHERE usuario_id IN ({criados})", o=self.orgs)
        for tabela in ("comprovantes_vinculo", "termos", "temas", "equipes"):
            self.sql(f"DELETE FROM {tabela} WHERE hackathon_id = :h", h=h)
        self.sql(
            "DELETE FROM hackathon WHERE id = :h OR organizacao_id = ANY(:o)", h=h, o=self.orgs
        )
        # Usuários criados pela API nos testes (os da fixture são apagados por ela)
        self.sql(
            "DELETE FROM usuarios WHERE organizacao_id = ANY(:o) AND email LIKE 'org_%'",
            o=self.orgs,
        )
        self.sql(
            "UPDATE usuarios SET organizacao_id = NULL WHERE organizacao_id = ANY(:o)", o=self.orgs
        )
        self.sql("DELETE FROM organizacoes WHERE id = ANY(:o)", o=self.orgs)


@pytest.fixture
def cenario(sql, usuario_no_banco):
    c = DuasOrganizacoes(sql, usuario_no_banco)
    try:
        yield c
    finally:
        c.limpar()


def test_hackathon_criado_pertence_a_organizacao_de_quem_cria(client, cenario):
    resposta = client.post(
        "/admin/hackathons",
        json={"nome": "Novo"},
        headers=com_token(cenario.org_b_organizador["id"]),
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["organizacao_id"] == str(cenario.org_b)
    assert resposta.json()["organizacao_nome"].startswith("Org B")


def test_painel_lista_so_os_hackathons_da_organizacao(client, cenario):
    de_a = client.get("/admin/hackathons", headers=com_token(cenario.org_a_organizador["id"]))
    de_b = client.get("/admin/hackathons", headers=com_token(cenario.org_b_organizador["id"]))

    assert str(cenario.hackathon_a) in [h["id"] for h in de_a.json()]
    assert str(cenario.hackathon_a) not in [h["id"] for h in de_b.json()]


def test_vitrine_filtra_por_organizacao(client, cenario):
    de_a = client.get("/hackathons", params={"organizacao_id": str(cenario.org_a)}).json()
    de_b = client.get("/hackathons", params={"organizacao_id": str(cenario.org_b)}).json()

    assert [h["id"] for h in de_a] == [str(cenario.hackathon_a)]
    assert de_b == []


@pytest.mark.parametrize(
    ("metodo", "caminho", "corpo"),
    [
        ("patch", "/admin/hackathons/{h}", {"nome": "Invadido"}),
        ("delete", "/admin/hackathons/{h}", None),
        ("post", "/hackathons/{h}/temas", {"titulo": "T", "descricao": "D", "ods": [1]}),
        ("get", "/hackathons/{h}/rubrica/rascunho", None),
        ("post", "/admin/hackathons/{h}/equipes/reavaliar", None),
        ("get", "/admin/hackathons/{h}/resultado", None),
        ("get", "/admin/hackathons/{h}/avaliacoes/designacoes", None),
        ("get", "/admin/hackathons/{h}/termos", None),
        (
            "post",
            "/admin/hackathons/{h}/termos",
            {"tipo": "REGULAMENTO", "versao": "1", "titulo": "R", "conteudo": "texto"},
        ),
    ],
)
def test_organizador_de_outra_organizacao_recebe_403(client, cenario, metodo, caminho, corpo):
    kwargs = {"headers": com_token(cenario.org_b_organizador["id"])}
    if corpo is not None:
        kwargs["json"] = corpo

    resposta = getattr(client, metodo)(caminho.format(h=cenario.hackathon_a), **kwargs)

    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "Este hackathon pertence a outra organização."}


def test_dev_gerencia_hackathon_de_qualquer_organizacao(client, cenario, usuario_no_banco):
    dev = usuario_no_banco(papel="DEV")

    resposta = client.patch(
        f"/admin/hackathons/{cenario.hackathon_a}",
        json={"local": "On-line"},
        headers=com_token(dev["id"]),
    )

    assert resposta.status_code == 200


def test_termos_publicados_pela_organizacao_viram_os_vigentes(client, cenario):
    cabecalho = com_token(cenario.org_a_organizador["id"])
    caminho = f"/admin/hackathons/{cenario.hackathon_a}/termos"
    for versao in ("1.0", "2.0"):
        resposta = client.post(
            caminho,
            json={
                "tipo": "REGULAMENTO",
                "versao": versao,
                "titulo": "Regulamento",
                "conteudo": "x",
            },
            headers=cabecalho,
        )
        assert resposta.status_code == 201, resposta.text
        publicada = client.post(f"{caminho}/{resposta.json()['id']}/publicar", headers=cabecalho)
        assert publicada.status_code == 200, publicada.text

    repetida = client.post(
        caminho,
        json={"tipo": "REGULAMENTO", "versao": "2.0", "titulo": "R", "conteudo": "x"},
        headers=cabecalho,
    )
    vigentes = client.get(f"/hackathons/{cenario.hackathon_a}/termos/vigentes")  # sem login

    assert repetida.status_code == 409
    assert vigentes.status_code == 200
    assert [(t["tipo"], t["versao"]) for t in vigentes.json()] == [("REGULAMENTO", "2.0")]
    assert len(client.get(caminho, headers=cabecalho).json()) == 2


def test_comprovantes_ficam_na_fila_da_organizacao_dona(client, cenario, usuario_no_banco):
    participante = usuario_no_banco()
    enviado = client.post(
        "/comprovantes",
        json={"arquivo_url": LINK, "hackathon_id": str(cenario.hackathon_a)},
        headers=com_token(participante["id"]),
    ).json()

    fila_a = client.get("/admin/comprovantes", headers=com_token(cenario.org_a_comite["id"]))
    fila_b = client.get("/admin/comprovantes", headers=com_token(cenario.org_b_comite["id"]))
    aprovar_b = client.post(
        f"/admin/comprovantes/{enviado['id']}/aprovar",
        headers=com_token(cenario.org_b_organizador["id"]),
    )
    aprovar_a = client.post(
        f"/admin/comprovantes/{enviado['id']}/aprovar",
        headers=com_token(cenario.org_a_comite["id"]),
    )

    assert enviado["id"] in [c["id"] for c in fila_a.json()]
    assert enviado["id"] not in [c["id"] for c in fila_b.json()]
    assert aprovar_b.status_code == 403
    assert aprovar_a.status_code == 200


def test_usuario_cadastrado_por_gestor_entra_na_organizacao_dele(client, cenario):
    resposta = client.post(
        "/admin/usuarios",
        json={
            "email": f"org_{uuid4().hex[:8]}@testes.com",
            "nome": "Avaliadora",
            "papel": "COMITE_TECNICO",
            "senha": "segredo123",
        },
        headers=com_token(cenario.org_a_organizador["id"]),
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["organizacao_id"] == str(cenario.org_a)


def test_minha_organizacao(client, cenario, usuario_no_banco):
    cabecalho = com_token(cenario.org_a_organizador["id"])

    editada = client.patch(
        "/organizacoes/minha", json={"descricao": "Sobre nós"}, headers=cabecalho
    )
    participante = client.get("/organizacoes/minha", headers=com_token(usuario_no_banco()["id"]))
    publica = client.get(f"/organizacoes/{cenario.org_a}")
    comite_edita = client.patch(
        "/organizacoes/minha", json={"nome": "X"}, headers=com_token(cenario.org_a_comite["id"])
    )

    assert editada.status_code == 200
    assert editada.json()["descricao"] == "Sobre nós"
    assert participante.status_code == 403
    assert publica.status_code == 200 and publica.json()["descricao"] == "Sobre nós"
    assert comite_edita.status_code == 403
    assert client.get(f"/organizacoes/{uuid4()}").status_code == 404


# --- Isolamento das rotas que vieram sem organização (mentores, treinamento, conteúdo,
# usuários e e-mails) ---


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("get", "/admin/hackathons/{h}/treinamento"),
        ("post", "/admin/hackathons/{h}/treinamento/concluir"),
        ("get", "/admin/hackathons/{h}/treinamento/sessoes"),
        ("get", "/admin/hackathons/{h}/faq"),
        ("get", "/admin/hackathons/{h}/apoiadores"),
        ("get", "/admin/hackathons/{h}/cronograma"),
        ("get", "/admin/equipes/{e}/mentoria"),
        ("get", "/admin/equipes/{e}/mentoria/historico"),
    ],
)
def test_rotas_do_hackathon_e_da_equipe_ficam_na_organizacao(client, cenario, metodo, caminho):
    equipe = cenario.sql(
        "INSERT INTO equipes (hackathon_id, nome) VALUES (:h, 'Equipe A') RETURNING id",
        h=cenario.hackathon_a,
    )[0]["id"]
    url = caminho.format(h=cenario.hackathon_a, e=equipe)

    resposta = getattr(client, metodo)(url, headers=com_token(cenario.org_b_organizador["id"]))

    assert resposta.status_code == 403, resposta.text
    assert resposta.json() == {"detail": "Este hackathon pertence a outra organização."}


def dados_de_mentor(hackathon_id) -> dict:
    return {
        "nome": "Mentora",
        "email": f"org_{uuid4().hex[:8]}@testes.com",
        "empresa_parceira": "Empresa",
        "area_atuacao": "Dados",
        "max_equipes": 2,
        "hackathon_id": str(hackathon_id),
    }


def test_mentor_pertence_a_organizacao_e_some_para_as_outras(client, cenario):
    cenario.publicar_termos()
    de_a = com_token(cenario.org_a_organizador["id"])
    de_b = com_token(cenario.org_b_organizador["id"])

    criado = client.post("/admin/mentores", json=dados_de_mentor(cenario.hackathon_a), headers=de_a)
    assert criado.status_code == 201, criado.text
    mentor = criado.json()
    lista_a = client.get("/admin/mentores", params={"limite": 100}, headers=de_a).json()
    lista_b = client.get("/admin/mentores", params={"limite": 100}, headers=de_b).json()

    assert mentor["organizacao_id"] == str(cenario.org_a)
    assert mentor["id"] in [m["id"] for m in lista_a]
    assert mentor["id"] not in [m["id"] for m in lista_b]
    assert client.get(f"/admin/mentores/{mentor['id']}", headers=de_a).status_code == 200
    for metodo, sufixo in [("get", ""), ("get", "/convites"), ("get", "/equipes")]:
        url = f"/admin/mentores/{mentor['id']}{sufixo}"
        assert getattr(client, metodo)(url, headers=de_b).status_code == 404
    assert client.post(f"/admin/mentores/{mentor['id']}/desativar", headers=de_b).status_code == 404


def test_outra_organizacao_nao_convida_mentor_para_o_hackathon_dela(client, cenario):
    cenario.publicar_termos()

    resposta = client.post(
        "/admin/mentores",
        json=dados_de_mentor(cenario.hackathon_a),
        headers=com_token(cenario.org_b_organizador["id"]),
    )

    assert resposta.status_code == 403


def test_fila_de_emails_mostra_so_a_organizacao(client, cenario):
    cenario.publicar_termos()
    de_a = com_token(cenario.org_a_organizador["id"])
    de_b = com_token(cenario.org_b_organizador["id"])
    dados = dados_de_mentor(cenario.hackathon_a)
    assert client.post("/admin/mentores", json=dados, headers=de_a).status_code == 201
    filtro = {"destinatario": dados["email"]}

    fila_a = client.get("/admin/emails", params=filtro, headers=de_a).json()
    fila_b = client.get("/admin/emails", params=filtro, headers=de_b).json()

    assert len(fila_a) == 1
    assert fila_b == []
    assert client.get(f"/admin/emails/{fila_a[0]['id']}", headers=de_b).status_code == 404
    assert client.post(f"/admin/emails/{fila_a[0]['id']}/reenviar", headers=de_b).status_code == 404


def test_gestao_de_usuarios_fica_na_organizacao(client, cenario):
    de_b = com_token(cenario.org_b_organizador["id"])
    alvo = cenario.org_a_comite["id"]

    lista = client.get("/admin/usuarios", params={"limite": 100}, headers=de_b).json()

    ids = [u["id"] for u in lista]
    assert str(cenario.org_b_comite["id"]) in ids
    assert str(alvo) not in ids and str(cenario.org_a_organizador["id"]) not in ids
    assert client.get(f"/admin/usuarios/{alvo}", headers=de_b).status_code == 404
    assert (
        client.patch(f"/admin/usuarios/{alvo}", json={"nome": "Invadido"}, headers=de_b).status_code
        == 404
    )
    assert client.post(f"/admin/usuarios/{alvo}/desativar", headers=de_b).status_code == 404


def test_ultimo_organizador_conta_por_organizacao(client, cenario, usuario_no_banco):
    """A organização A tem um só Organizador: mesmo com Organizadores em outras organizações,
    ele não pode ser desativado."""
    dev = usuario_no_banco(papel="DEV")

    resposta = client.post(
        f"/admin/usuarios/{cenario.org_a_organizador['id']}/desativar",
        headers=com_token(dev["id"]),
    )

    assert resposta.status_code == 409
