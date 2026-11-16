"""
Conteúdo institucional da edição (BE-S5-12): página pública, apoiadores, FAQ, cronograma,
regulamento com versões e treinamento (RF10 a RF14, RF35, RF59; RN05; RNF20).

Estes testes gravam no banco de verdade; a fixture `edicao` apaga tudo no final.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.security.token import criar_token

LINK = "https://exemplo.com/arquivo.pdf"
LOGO = "https://cdn.exemplo.com/logo.png"


def cab(usuario: dict) -> dict:
    return {"Authorization": f"Bearer {criar_token(usuario['id'])}"}


def iso(dias: float) -> str:
    return (datetime.now(UTC) + timedelta(days=dias)).isoformat()


TABELAS_DA_EDICAO = (
    "materiais_treinamento",  # filhos de sessoes_treinamento, tratados à parte
    "sessoes_treinamento",
    "apoiadores",
    "faq_itens",
    "fases_cronograma",
    "resultados_proposta",
    "homologacoes_resultado",
    "membros_equipe",
    "submissoes",
    "temas",
    "equipes",
    "termos",
)


@pytest.fixture
def edicao(sql, usuario_no_banco):
    """Cria edições de teste e as apaga, com todo o conteúdo ligado a elas, no final."""
    ids: list = []

    def criar(status: str = "ATIVO", **campos) -> str:
        colunas = {"nome": "Edição de teste", "status": status, **campos}
        nomes = ", ".join(colunas)
        valores = ", ".join(
            "CAST(:status AS status_hackathon)" if c == "status" else f":{c}" for c in colunas
        )
        id_ = sql(f"INSERT INTO hackathon ({nomes}) VALUES ({valores}) RETURNING id", **colunas)[0][
            "id"
        ]
        ids.append(id_)
        return str(id_)

    yield criar
    if ids:
        sql(
            "DELETE FROM materiais_treinamento WHERE sessao_id IN"
            " (SELECT id FROM sessoes_treinamento WHERE hackathon_id = ANY(:h))",
            h=ids,
        )
        sql(
            "DELETE FROM aceites_termos WHERE termo_id IN"
            " (SELECT id FROM termos WHERE hackathon_id = ANY(:h))",
            h=ids,
        )
        for tabela in TABELAS_DA_EDICAO[1:]:
            sql(f"DELETE FROM {tabela} WHERE hackathon_id = ANY(:h)", h=ids)
        sql("DELETE FROM hackathon WHERE id = ANY(:h)", h=ids)


@pytest.fixture
def org(usuario_no_banco):
    return usuario_no_banco(papel="ORGANIZADOR", senha=None)


@pytest.fixture
def ed(edicao):
    return edicao()


def base(h: str) -> str:
    return f"/admin/hackathons/{h}"


def publico(h: str) -> str:
    return f"/publico/hackathons/{h}"


# --- Permissões das rotas administrativas ---

ROTAS_ADMIN = [
    ("POST", "/apoiadores", {"nome": "A", "categoria": "C"}),
    ("GET", "/apoiadores", None),
    ("PATCH", f"/apoiadores/{uuid4()}", {"nome": "B"}),
    ("DELETE", f"/apoiadores/{uuid4()}", None),
    ("POST", "/faq", {"pergunta": "P?", "resposta": "R"}),
    ("GET", "/faq", None),
    ("PUT", "/faq/ordem", {"ids": [str(uuid4())]}),
    ("PATCH", f"/faq/{uuid4()}", {"pergunta": "Q?"}),
    ("DELETE", f"/faq/{uuid4()}", None),
    ("GET", "/cronograma", None),
    (
        "POST",
        "/cronograma",
        {"nome": "F", "inicio": "2030-01-01T00:00:00Z", "fim": "2030-01-02T00:00:00Z"},
    ),
    ("PATCH", f"/cronograma/{uuid4()}", {"nome": "G"}),
    ("DELETE", f"/cronograma/{uuid4()}", None),
    ("POST", "/termos", {"versao": "1", "titulo": "T", "conteudo": "x"}),
    ("GET", "/termos", None),
    ("PATCH", f"/termos/{uuid4()}", {"titulo": "T2"}),
    ("DELETE", f"/termos/{uuid4()}", None),
    ("POST", f"/termos/{uuid4()}/publicar", None),
    (
        "POST",
        "/treinamento/sessoes",
        {"titulo": "S", "inicio": "2030-01-01T00:00:00Z", "local": "L"},
    ),
    ("GET", "/treinamento/sessoes", None),
    ("PATCH", f"/treinamento/sessoes/{uuid4()}", {"titulo": "S2"}),
    ("DELETE", f"/treinamento/sessoes/{uuid4()}", None),
    ("POST", f"/treinamento/sessoes/{uuid4()}/materiais", {"titulo": "M", "url": LINK}),
    ("DELETE", f"/treinamento/sessoes/{uuid4()}/materiais/{uuid4()}", None),
]


def chamar(client, metodo, caminho, corpo, headers=None):
    return client.request(metodo, caminho, json=corpo, headers=headers or {})


@pytest.mark.parametrize("metodo, caminho, corpo", ROTAS_ADMIN)
def test_sem_token_recebe_401(client, ed, metodo, caminho, corpo):
    assert chamar(client, metodo, base(ed) + caminho, corpo).status_code == 401


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO", "COMITE_CIENTIFICO"])
@pytest.mark.parametrize("metodo, caminho, corpo", ROTAS_ADMIN)
def test_perfis_sem_gestao_recebem_403(client, ed, usuario_no_banco, papel, metodo, caminho, corpo):
    usuario = usuario_no_banco(papel=papel, senha=None)

    resposta = chamar(client, metodo, base(ed) + caminho, corpo, cab(usuario))

    assert resposta.status_code == 403


def test_conta_pendente_recebe_403(client, ed, usuario_no_banco):
    usuario = usuario_no_banco(papel="PARTICIPANTE", senha=None, situacao_conta="PENDENTE")

    assert client.get(base(ed) + "/faq", headers=cab(usuario)).status_code == 403


@pytest.mark.parametrize("papel", ["ORGANIZADOR", "DEV"])
def test_organizador_e_dev_gerenciam(client, ed, usuario_no_banco, papel):
    usuario = usuario_no_banco(papel=papel, senha=None)

    resposta = client.post(
        base(ed) + "/faq", json={"pergunta": "P?", "resposta": "R"}, headers=cab(usuario)
    )

    assert resposta.status_code == 201


def test_edicao_inexistente_recebe_404(client, org):
    h = str(uuid4())
    for caminho in ("/faq", "/apoiadores", "/cronograma", "/termos", "/treinamento/sessoes"):
        assert client.get(base(h) + caminho, headers=cab(org)).status_code == 404, caminho


# --- Página pública (RF10) ---


def test_pagina_publica_abre_sem_login(client, edicao):
    h = edicao(
        nome="Hackathon 2030",
        tema="Cidades",
        descricao="Evento de inovação.",
        data_inicio=datetime(2030, 5, 1),
        data_fim=datetime(2030, 5, 3),
    )

    resposta = client.get(publico(h))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["nome"] == "Hackathon 2030"
    assert corpo["descricao"] == "Evento de inovação."
    assert corpo["data_inicio"].startswith("2030-05-01")
    assert corpo["inscricoes_abertas"] is False
    assert (corpo["regulamento"], corpo["faq"], corpo["apoiadores"]) == (None, [], [])


def test_inscricoes_abertas_segue_a_rn06(client, edicao):
    aberta = edicao(status="INSCRICOES")
    encerrada = edicao(status="INSCRICOES_ENCERRADAS")

    assert client.get(publico(aberta)).json()["inscricoes_abertas"] is True
    assert client.get(publico(encerrada)).json()["inscricoes_abertas"] is False


def test_edicao_em_rascunho_nao_aparece_para_o_publico(client, edicao):
    h = edicao(status="RASCUNHO")

    for sufixo in ("", "/regulamento", "/faq", "/cronograma", "/apoiadores"):
        assert client.get(publico(h) + sufixo).status_code == 404, sufixo
    ids = {e["id"] for e in client.get("/publico/hackathons", params={"limite": 100}).json()}
    assert h not in ids


def test_edicao_inexistente_e_404_no_publico(client):
    for sufixo in ("", "/regulamento", "/faq", "/cronograma", "/apoiadores"):
        assert client.get(publico(str(uuid4())) + sufixo).status_code == 404, sufixo


def test_lista_publica_traz_so_divulgadas_e_pagina(client, edicao):
    visivel = edicao(status="ATIVO", data_inicio=datetime(2099, 1, 1))
    edicao(status="RASCUNHO", data_inicio=datetime(2099, 2, 1))

    resposta = client.get("/publico/hackathons", params={"limite": 100})

    assert resposta.status_code == 200
    assert visivel in {e["id"] for e in resposta.json()}
    assert all(e["status"] != "RASCUNHO" for e in resposta.json())
    assert client.get("/publico/hackathons", params={"limite": 1}).json().__len__() == 1
    assert client.get("/publico/hackathons", params={"limite": 0}).status_code == 422


def test_crud_de_hackathon_aceita_descricao_sem_quebrar_o_contrato(client, org):
    criado = client.post("/admin/hackathons", json={"nome": "Sem descrição"}, headers=cab(org))
    com = client.post(
        "/admin/hackathons", json={"nome": "Com", "descricao": "Texto"}, headers=cab(org)
    )
    try:
        assert criado.status_code == com.status_code == 201
        assert criado.json()["descricao"] is None
        editado = client.patch(
            f"/admin/hackathons/{criado.json()['id']}",
            json={"descricao": "Nova"},
            headers=cab(org),
        )
        assert editado.json()["descricao"] == "Nova"
        assert com.json()["descricao"] == "Texto"
    finally:
        for r in (criado, com):
            client.delete(f"/admin/hackathons/{r.json()['id']}", headers=cab(org))


# --- Apoiadores (RF14) ---


def novo_apoiador(client, org, h, **campos):
    corpo = {"nome": "Apoio", "categoria": "Apoio", **campos}
    resposta = client.post(base(h) + "/apoiadores", json=corpo, headers=cab(org))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_apoiador_nasce_nao_publicado_e_so_aparece_depois(client, org, ed):
    apoiador = novo_apoiador(client, org, ed, nome="Açaí Valley", logo_url=LOGO, site_url=LINK)

    assert apoiador["publicado"] is False
    assert client.get(publico(ed) + "/apoiadores").json() == []
    client.patch(
        base(ed) + f"/apoiadores/{apoiador['id']}", json={"publicado": True}, headers=cab(org)
    )
    [grupo] = client.get(publico(ed) + "/apoiadores").json()
    assert grupo["categoria"] == "Apoio"
    assert grupo["apoiadores"] == [{"nome": "Açaí Valley", "logo_url": LOGO, "site_url": LINK}]


def test_apoiadores_agrupados_por_categoria_na_ordem(client, org, ed):
    for nome, categoria in [("A", "Patrocinador"), ("B", "Apoio"), ("C", "Patrocinador")]:
        novo_apoiador(client, org, ed, nome=nome, categoria=categoria, publicado=True)
    novo_apoiador(client, org, ed, nome="Oculto", categoria="Apoio")

    grupos = client.get(publico(ed) + "/apoiadores").json()

    assert [g["categoria"] for g in grupos] == ["Patrocinador", "Apoio"]
    assert [a["nome"] for a in grupos[0]["apoiadores"]] == ["A", "C"]
    assert [a["nome"] for a in grupos[1]["apoiadores"]] == ["B"]


def test_apoiadores_aparecem_na_pagina_publica(client, org, ed):
    novo_apoiador(client, org, ed, publicado=True)

    assert len(client.get(publico(ed)).json()["apoiadores"]) == 1


def test_listar_apoiadores_filtra_e_pagina(client, org, ed):
    for n in range(3):
        novo_apoiador(
            client, org, ed, nome=f"N{n}", categoria="X" if n < 2 else "Y", publicado=n == 0
        )
    cabecalho = cab(org)

    todos = client.get(base(ed) + "/apoiadores", headers=cabecalho).json()
    publicados = client.get(base(ed) + "/apoiadores?publicado=true", headers=cabecalho).json()
    da_categoria = client.get(base(ed) + "/apoiadores?categoria=Y", headers=cabecalho).json()
    pagina = client.get(base(ed) + "/apoiadores?limite=2&deslocamento=2", headers=cabecalho).json()

    assert [a["nome"] for a in todos] == ["N0", "N1", "N2"]
    assert [a["nome"] for a in publicados] == ["N0"]
    assert [a["nome"] for a in da_categoria] == ["N2"]
    assert [a["nome"] for a in pagina] == ["N2"]
    assert client.get(base(ed) + "/apoiadores?limite=101", headers=cabecalho).status_code == 422


def test_editar_apoiador_limpa_links_e_muda_a_ordem(client, org, ed):
    a = novo_apoiador(client, org, ed, logo_url=LOGO, site_url=LINK)

    resposta = client.patch(
        base(ed) + f"/apoiadores/{a['id']}",
        json={"logo_url": None, "site_url": None, "ordem": 7},
        headers=cab(org),
    )

    assert resposta.status_code == 200
    assert (resposta.json()["logo_url"], resposta.json()["site_url"], resposta.json()["ordem"]) == (
        None,
        None,
        7,
    )


@pytest.mark.parametrize("campo", ["nome", "categoria", "ordem", "publicado"])
def test_editar_apoiador_recusa_nulo(client, org, ed, campo):
    a = novo_apoiador(client, org, ed)

    resposta = client.patch(
        base(ed) + f"/apoiadores/{a['id']}", json={campo: None}, headers=cab(org)
    )

    assert resposta.status_code == 422


def test_excluir_apoiador(client, org, ed):
    a = novo_apoiador(client, org, ed)

    assert client.delete(base(ed) + f"/apoiadores/{a['id']}", headers=cab(org)).status_code == 204
    assert client.delete(base(ed) + f"/apoiadores/{a['id']}", headers=cab(org)).status_code == 404


def test_item_de_outra_edicao_nao_e_encontrado(client, org, edicao):
    h1, h2 = edicao(), edicao()
    a = novo_apoiador(client, org, h1)

    assert (
        client.patch(
            base(h2) + f"/apoiadores/{a['id']}", json={"nome": "X"}, headers=cab(org)
        ).status_code
        == 404
    )
    assert client.delete(base(h2) + f"/apoiadores/{a['id']}", headers=cab(org)).status_code == 404


# --- Política de links (RNF20) ---


@pytest.mark.parametrize(
    "link",
    [
        "http://exemplo.com/logo.png",
        "ftp://exemplo.com/logo.png",
        "javascript:alert(1).png",
        "//exemplo.com/logo.png",
        "https://user:senha@exemplo.com/logo.png",
        "https://exemplo.com/logo com espaco.png",
        "https://exemplo.com/logo\n.png",
        "https://exemplo.com/lo\tgo.png",
        "https://",
        "https://exemplo.com/" + "a" * 2050 + ".png",
        "https://exemplo.com/arquivo.pdf",  # não é imagem
    ],
)
def test_logo_fora_da_politica(client, org, ed, link):
    resposta = client.post(
        base(ed) + "/apoiadores",
        json={"nome": "A", "categoria": "C", "logo_url": link},
        headers=cab(org),
    )

    assert resposta.status_code == 422


def test_espacos_e_quebras_nas_pontas_do_link_sao_aparados(client, org, ed):
    resposta = client.post(
        base(ed) + "/apoiadores",
        json={"nome": "A", "categoria": "C", "logo_url": "  https://exemplo.com/logo.png\n"},
        headers=cab(org),
    )

    assert resposta.status_code == 201
    assert resposta.json()["logo_url"] == "https://exemplo.com/logo.png"


@pytest.mark.parametrize("link", ["http://exemplo.com", "javascript:alert(1)", "https://u:p@x.com"])
def test_site_fora_da_politica(client, org, ed, link):
    resposta = client.post(
        base(ed) + "/apoiadores",
        json={"nome": "A", "categoria": "C", "site_url": link},
        headers=cab(org),
    )

    assert resposta.status_code == 422


@pytest.mark.parametrize("extensao", ["png", "jpg", "jpeg", "webp", "svg", "SVG"])
def test_logo_aceita_imagens(client, org, ed, extensao):
    resposta = client.post(
        base(ed) + "/apoiadores",
        json={
            "nome": "A",
            "categoria": "C",
            "logo_url": f"https://cdn.exemplo.com/l.{extensao}?v=1",
        },
        headers=cab(org),
    )

    assert resposta.status_code == 201


def test_a_api_nao_aceita_arquivo(client, org, ed):
    resposta = client.post(
        base(ed) + "/apoiadores",
        files={"logo": ("logo.png", b"conteudo-do-arquivo", "image/png")},
        headers=cab(org),
    )

    assert resposta.status_code == 422


# --- FAQ (RF12) ---


def nova_pergunta(client, org, h, n=0, **campos):
    corpo = {"pergunta": f"Pergunta {n}?", "resposta": f"Resposta {n}", **campos}
    resposta = client.post(base(h) + "/faq", json=corpo, headers=cab(org))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_faq_so_publicadas_e_na_ordem(client, org, ed):
    a, b, c = (nova_pergunta(client, org, ed, n, publicado=n != 1) for n in range(3))

    assert [a["ordem"], b["ordem"], c["ordem"]] == [0, 1, 2]
    publico_faq = client.get(publico(ed) + "/faq").json()
    assert [p["pergunta"] for p in publico_faq] == ["Pergunta 0?", "Pergunta 2?"]
    assert set(publico_faq[0]) == {"id", "pergunta", "resposta"}
    assert [p["pergunta"] for p in client.get(publico(ed)).json()["faq"]] == [
        "Pergunta 0?",
        "Pergunta 2?",
    ]


def test_reordenar_faq(client, org, ed):
    itens = [nova_pergunta(client, org, ed, n, publicado=True) for n in range(3)]
    nova_ordem = [itens[2]["id"], itens[0]["id"], itens[1]["id"]]

    resposta = client.put(base(ed) + "/faq/ordem", json={"ids": nova_ordem}, headers=cab(org))

    assert resposta.status_code == 200
    assert [i["id"] for i in resposta.json()] == nova_ordem
    assert [i["ordem"] for i in resposta.json()] == [0, 1, 2]
    assert [p["id"] for p in client.get(publico(ed) + "/faq").json()] == nova_ordem
    assert [i["id"] for i in client.get(base(ed) + "/faq", headers=cab(org)).json()] == nova_ordem


def test_reordenar_exige_todas_as_perguntas(client, org, ed, edicao):
    itens = [nova_pergunta(client, org, ed, n) for n in range(3)]
    outra = nova_pergunta(client, org, edicao(), 9)
    ids = [i["id"] for i in itens]

    faltando = client.put(base(ed) + "/faq/ordem", json={"ids": ids[:2]}, headers=cab(org))
    de_fora = client.put(
        base(ed) + "/faq/ordem", json={"ids": [*ids, outra["id"]]}, headers=cab(org)
    )
    repetido = client.put(
        base(ed) + "/faq/ordem", json={"ids": [ids[0], ids[0], *ids[1:]]}, headers=cab(org)
    )
    vazio = client.put(base(ed) + "/faq/ordem", json={"ids": []}, headers=cab(org))

    assert faltando.status_code == de_fora.status_code == 409
    assert repetido.status_code == vazio.status_code == 422
    assert [i["id"] for i in client.get(base(ed) + "/faq", headers=cab(org)).json()] == ids


def test_editar_e_excluir_pergunta(client, org, ed):
    p = nova_pergunta(client, org, ed)

    editada = client.patch(
        base(ed) + f"/faq/{p['id']}", json={"resposta": "Nova", "publicado": True}, headers=cab(org)
    )

    assert editada.json()["resposta"] == "Nova"
    assert [x["resposta"] for x in client.get(publico(ed) + "/faq").json()] == ["Nova"]
    assert client.delete(base(ed) + f"/faq/{p['id']}", headers=cab(org)).status_code == 204
    assert client.get(publico(ed) + "/faq").json() == []
    assert (
        client.patch(
            base(ed) + f"/faq/{p['id']}", json={"resposta": "x"}, headers=cab(org)
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "corpo",
    [
        {"pergunta": " ", "resposta": "R"},
        {"pergunta": "P", "resposta": ""},
        {"pergunta": "P"},
        {"pergunta": "P", "resposta": "R", "ordem": 3},
    ],
)
def test_pergunta_invalida(client, org, ed, corpo):
    assert client.post(base(ed) + "/faq", json=corpo, headers=cab(org)).status_code == 422


def test_listar_faq_filtra_e_pagina(client, org, ed):
    for n in range(3):
        nova_pergunta(client, org, ed, n, publicado=n == 1)

    publicadas = client.get(base(ed) + "/faq?publicado=true", headers=cab(org)).json()
    rascunhos = client.get(base(ed) + "/faq?publicado=false", headers=cab(org)).json()
    pagina = client.get(base(ed) + "/faq?limite=1&deslocamento=1", headers=cab(org)).json()

    assert len(publicadas) == 1 and len(rascunhos) == 2
    assert [p["pergunta"] for p in pagina] == ["Pergunta 1?"]


def test_criacoes_simultaneas_recebem_posicoes_distintas(client, org, ed):
    with ThreadPoolExecutor(max_workers=6) as pool:
        futuros = [pool.submit(nova_pergunta, client, org, ed, n) for n in range(6)]
        [f.result() for f in futuros]

    ordens = [i["ordem"] for i in client.get(base(ed) + "/faq", headers=cab(org)).json()]
    assert sorted(ordens) == [0, 1, 2, 3, 4, 5]


def test_reordenacoes_simultaneas_deixam_uma_ordem_valida(client, org, ed):
    ids = [nova_pergunta(client, org, ed, n)["id"] for n in range(4)]
    a, b = ids[::-1], [ids[1], ids[0], ids[3], ids[2]]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [
            pool.submit(client.put, base(ed) + "/faq/ordem", json={"ids": ordem}, headers=cab(org))
            for ordem in (a, b)
        ]
        codigos = [f.result().status_code for f in futuros]

    assert codigos == [200, 200]
    final = [i["id"] for i in client.get(base(ed) + "/faq", headers=cab(org)).json()]
    assert final in (a, b)
    ordens = [i["ordem"] for i in client.get(base(ed) + "/faq", headers=cab(org)).json()]
    assert ordens == [0, 1, 2, 3]


# --- Cronograma (RF13, RF59) ---


def nova_fase(client, org, h, **campos):
    corpo = {"nome": "Fase", "inicio": iso(1), "fim": iso(2), **campos}
    resposta = client.post(base(h) + "/cronograma", json=corpo, headers=cab(org))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_cronograma_traz_as_datas_do_edital_em_ordem_e_destaca_a_atual(client, edicao):
    agora = datetime.now(UTC).replace(tzinfo=None)
    h = edicao(
        inscricoes_inicio=agora - timedelta(days=10),
        inscricoes_fim=agora - timedelta(days=5),
        homologacao_fim=agora + timedelta(days=5),
        propostas_inicio=agora - timedelta(days=1),
        propostas_fim=agora + timedelta(days=9),
    )

    linhas = client.get(publico(h) + "/cronograma").json()

    assert [linha["nome"] for linha in linhas] == [
        "Inscrições",
        "Homologação das equipes",
        "Envio de propostas",
    ]
    assert [linha["situacao"] for linha in linhas] == ["ENCERRADA", "EM_ANDAMENTO", "EM_ANDAMENTO"]
    assert [linha["atual"] for linha in linhas] == [False, True, True]
    assert all(linha["origem"] == "EDITAL" and linha["id"] is None for linha in linhas)
    inicios = [linha["inicio"] for linha in linhas]
    assert inicios == sorted(inicios)


def test_cronograma_segue_as_datas_do_hackathon(client, org, edicao):
    h = edicao(propostas_inicio=datetime(2031, 1, 1), propostas_fim=datetime(2031, 1, 10))
    antes = client.get(publico(h) + "/cronograma").json()

    client.patch(
        f"/admin/hackathons/{h}",
        json={"propostas_inicio": "2031-02-01T00:00:00Z", "propostas_fim": "2031-02-10T00:00:00Z"},
        headers=cab(org),
    )
    depois = client.get(publico(h) + "/cronograma").json()

    assert antes[0]["inicio"].startswith("2031-01-01")
    assert depois[0]["inicio"].startswith("2031-02-01")


def test_cronograma_sem_datas_do_edital_comeca_vazio(client, ed):
    assert client.get(publico(ed) + "/cronograma").json() == []


def test_fases_publicadas_entram_em_ordem_cronologica(client, org, ed):
    tarde = nova_fase(client, org, ed, nome="Tarde", inicio=iso(20), fim=iso(21), publicado=True)
    cedo = nova_fase(client, org, ed, nome="Cedo", inicio=iso(3), fim=iso(4), publicado=True)
    nova_fase(client, org, ed, nome="Oculta", inicio=iso(1), fim=iso(2))

    publico_linhas = client.get(publico(ed) + "/cronograma").json()
    admin_linhas = client.get(base(ed) + "/cronograma", headers=cab(org)).json()

    assert [x["nome"] for x in publico_linhas] == ["Cedo", "Tarde"]
    assert [x["id"] for x in publico_linhas] == [cedo["id"], tarde["id"]]
    assert [x["nome"] for x in admin_linhas] == ["Oculta", "Cedo", "Tarde"]
    assert [x["publicado"] for x in admin_linhas] == [False, True, True]
    assert all(x["origem"] == "PERSONALIZADA" for x in admin_linhas)


def test_fase_atual_e_destacada(client, org, ed):
    nova_fase(client, org, ed, nome="Passada", inicio=iso(-5), fim=iso(-4), publicado=True)
    nova_fase(client, org, ed, nome="Agora", inicio=iso(-1), fim=iso(1), publicado=True)
    nova_fase(client, org, ed, nome="Futura", inicio=iso(4), fim=iso(5), publicado=True)

    linhas = client.get(publico(ed) + "/cronograma").json()

    assert [(x["nome"], x["situacao"], x["atual"]) for x in linhas] == [
        ("Passada", "ENCERRADA", False),
        ("Agora", "EM_ANDAMENTO", True),
        ("Futura", "NAO_INICIADA", False),
    ]


def test_cronograma_aparece_na_pagina_publica(client, org, ed):
    nova_fase(client, org, ed, nome="Visível", publicado=True)

    assert [x["nome"] for x in client.get(publico(ed)).json()["cronograma"]] == ["Visível"]


def test_fase_com_fim_antes_do_inicio(client, org, ed):
    resposta = client.post(
        base(ed) + "/cronograma",
        json={"nome": "F", "inicio": iso(5), "fim": iso(4)},
        headers=cab(org),
    )

    assert resposta.status_code == 422


def test_editar_fase_valida_o_periodo_final(client, org, ed):
    fase = nova_fase(client, org, ed, inicio=iso(5), fim=iso(6))
    caminho = base(ed) + f"/cronograma/{fase['id']}"

    so_o_fim = client.patch(caminho, json={"fim": iso(4)}, headers=cab(org))
    so_o_inicio = client.patch(caminho, json={"inicio": iso(7)}, headers=cab(org))
    certo = client.patch(
        caminho, json={"inicio": iso(2), "fim": iso(3), "publicado": True}, headers=cab(org)
    )

    assert so_o_fim.status_code == so_o_inicio.status_code == 422
    assert certo.status_code == 200 and certo.json()["publicado"] is True


def test_fase_sem_fuso_vale_como_utc_e_com_fuso_e_convertida(client, org, ed):
    sem_fuso = nova_fase(client, org, ed, inicio="2030-06-01T12:00:00", fim="2030-06-01T13:00:00")
    com_fuso = nova_fase(
        client, org, ed, inicio="2030-06-01T12:00:00-03:00", fim="2030-06-01T13:00:00-03:00"
    )

    assert sem_fuso["inicio"].startswith("2030-06-01T12:00:00")
    assert com_fuso["inicio"].startswith("2030-06-01T15:00:00")


@pytest.mark.parametrize(
    "corpo",
    [
        {"nome": "F"},
        {"nome": "", "inicio": "2030-01-01T00:00:00Z", "fim": "2030-01-02T00:00:00Z"},
        {"nome": "F", "inicio": "ontem", "fim": "amanhã"},
    ],
)
def test_fase_invalida(client, org, ed, corpo):
    assert client.post(base(ed) + "/cronograma", json=corpo, headers=cab(org)).status_code == 422


def test_excluir_fase(client, org, ed):
    fase = nova_fase(client, org, ed)

    assert (
        client.delete(base(ed) + f"/cronograma/{fase['id']}", headers=cab(org)).status_code == 204
    )
    assert (
        client.delete(base(ed) + f"/cronograma/{fase['id']}", headers=cab(org)).status_code == 404
    )


# --- Regulamento com versões (RF11, RN05) ---


def novo_rascunho(client, org, h, versao="1.0", **campos):
    corpo = {
        "versao": versao,
        "titulo": f"Regulamento {versao}",
        "conteudo": f"Texto {versao}",
        **campos,
    }
    resposta = client.post(base(h) + "/termos", json=corpo, headers=cab(org))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def publicar(client, org, h, termo):
    return client.post(base(h) + f"/termos/{termo['id']}/publicar", headers=cab(org))


def test_rascunho_nao_aparece_para_o_publico(client, org, ed):
    rascunho = novo_rascunho(client, org, ed)

    assert (rascunho["rascunho"], rascunho["vigente"], rascunho["publicado_em"]) == (
        True,
        False,
        None,
    )
    assert rascunho["tipo"] == "REGULAMENTO"
    assert client.get(publico(ed) + "/regulamento").status_code == 404
    assert client.get(publico(ed)).json()["regulamento"] is None
    vigentes = client.get(f"/hackathons/{ed}/termos/vigentes", headers=cab(org))
    assert vigentes.json() == []


def test_publicar_torna_vigente_e_mostra_a_data(client, org, ed):
    rascunho = novo_rascunho(client, org, ed)

    resposta = publicar(client, org, ed, rascunho)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["vigente"], corpo["rascunho"]) == (True, False)
    assert corpo["publicado_em"] is not None
    visivel = client.get(publico(ed) + "/regulamento").json()
    assert visivel["versao"] == "1.0"
    assert visivel["publicado_em"] == corpo["publicado_em"]
    assert client.get(publico(ed)).json()["regulamento"]["titulo"] == "Regulamento 1.0"
    [termo] = client.get(f"/hackathons/{ed}/termos/vigentes", headers=cab(org)).json()
    assert termo["id"] == rascunho["id"]


def test_nova_versao_substitui_a_vigente(client, org, ed):
    v1 = novo_rascunho(client, org, ed, "1.0")
    publicar(client, org, ed, v1)
    v2 = novo_rascunho(client, org, ed, "2.0")
    assert client.get(publico(ed) + "/regulamento").json()["versao"] == "1.0"

    publicar(client, org, ed, v2)

    assert client.get(publico(ed) + "/regulamento").json()["versao"] == "2.0"
    versoes = client.get(base(ed) + "/termos", headers=cab(org)).json()
    por_versao = {v["versao"]: v for v in versoes}
    assert por_versao["1.0"]["vigente"] is False and por_versao["1.0"]["rascunho"] is False
    assert por_versao["2.0"]["vigente"] is True
    assert sum(v["vigente"] for v in versoes) == 1


def test_publicar_de_novo_a_vigente_nao_muda_nada(client, org, ed):
    v1 = publicar(client, org, ed, novo_rascunho(client, org, ed)).json()

    de_novo = publicar(client, org, ed, v1)

    assert de_novo.status_code == 200
    assert de_novo.json()["publicado_em"] == v1["publicado_em"]


def test_versao_substituida_nao_volta_a_vigorar(client, org, ed):
    v1 = novo_rascunho(client, org, ed, "1.0")
    publicar(client, org, ed, v1)
    publicar(client, org, ed, novo_rascunho(client, org, ed, "2.0"))

    assert publicar(client, org, ed, v1).status_code == 409


def test_versao_publicada_e_imutavel(client, org, ed):
    v1 = publicar(client, org, ed, novo_rascunho(client, org, ed)).json()
    caminho = base(ed) + f"/termos/{v1['id']}"

    assert client.patch(caminho, json={"titulo": "Outro"}, headers=cab(org)).status_code == 409
    assert client.delete(caminho, headers=cab(org)).status_code == 409
    assert client.get(publico(ed) + "/regulamento").json()["titulo"] == v1["titulo"]


def test_editar_e_excluir_rascunho(client, org, ed):
    r = novo_rascunho(client, org, ed, url=LINK)
    caminho = base(ed) + f"/termos/{r['id']}"

    editado = client.patch(
        caminho, json={"titulo": "Novo título", "conteudo": None}, headers=cab(org)
    )
    sem_documento = client.patch(caminho, json={"url": None}, headers=cab(org))

    assert editado.status_code == 200
    assert (editado.json()["titulo"], editado.json()["conteudo"], editado.json()["url"]) == (
        "Novo título",
        None,
        LINK,
    )
    assert sem_documento.status_code == 422
    assert client.patch(caminho, json={"versao": "9"}, headers=cab(org)).status_code == 422
    assert client.delete(caminho, headers=cab(org)).status_code == 204
    assert client.delete(caminho, headers=cab(org)).status_code == 404


def test_versao_repetida_e_documento_obrigatorio(client, org, ed):
    novo_rascunho(client, org, ed, "1.0")

    repetida = client.post(
        base(ed) + "/termos",
        json={"versao": "1.0", "titulo": "T", "conteudo": "x"},
        headers=cab(org),
    )
    sem_documento = client.post(
        base(ed) + "/termos", json={"versao": "3", "titulo": "T"}, headers=cab(org)
    )
    link_ruim = client.post(
        base(ed) + "/termos",
        json={"versao": "3", "titulo": "T", "url": "http://x.com/a.pdf"},
        headers=cab(org),
    )

    assert repetida.status_code == 409
    assert sem_documento.status_code == link_ruim.status_code == 422


def test_o_mesmo_numero_vale_em_tipos_e_edicoes_diferentes(client, org, edicao):
    h1, h2 = edicao(), edicao()
    novo_rascunho(client, org, h1, "1.0")

    assert (
        novo_rascunho(client, org, h1, "1.0", tipo="TERMO_CONSENTIMENTO")["tipo"]
        == "TERMO_CONSENTIMENTO"
    )
    assert novo_rascunho(client, org, h2, "1.0")["hackathon_id"] == h2


def test_publicar_um_tipo_nao_mexe_no_outro(client, org, ed):
    reg = publicar(client, org, ed, novo_rascunho(client, org, ed, "1.0")).json()
    termo = publicar(
        client, org, ed, novo_rascunho(client, org, ed, "1.0", tipo="TERMO_CONSENTIMENTO")
    ).json()

    vigentes = client.get(f"/hackathons/{ed}/termos/vigentes", headers=cab(org)).json()

    assert {v["id"] for v in vigentes} == {reg["id"], termo["id"]}


def test_aceite_antigo_continua_ligado_a_versao_aceita(client, org, sql, ed, usuario_no_banco):
    v1 = publicar(client, org, ed, novo_rascunho(client, org, ed, "1.0")).json()
    pessoa = usuario_no_banco(senha=None)
    sql(
        "INSERT INTO aceites_termos (termo_id, usuario_id) VALUES (:t, :u)",
        t=v1["id"],
        u=pessoa["id"],
    )

    publicar(client, org, ed, novo_rascunho(client, org, ed, "2.0"))

    [aceite] = sql("SELECT termo_id FROM aceites_termos WHERE usuario_id = :u", u=pessoa["id"])
    assert str(aceite["termo_id"]) == v1["id"]


def test_listar_versoes_filtra_e_pagina(client, org, ed):
    for versao in ("1", "2", "3"):
        novo_rascunho(client, org, ed, versao)
    publicar(client, org, ed, client.get(base(ed) + "/termos", headers=cab(org)).json()[0])
    novo_rascunho(client, org, ed, "9", tipo="TERMO_CONSENTIMENTO")

    rascunhos = client.get(base(ed) + "/termos?rascunho=true", headers=cab(org)).json()
    do_regulamento = client.get(base(ed) + "/termos?tipo=REGULAMENTO", headers=cab(org)).json()
    pagina = client.get(base(ed) + "/termos?limite=2", headers=cab(org)).json()

    assert len(rascunhos) == 3
    assert len(do_regulamento) == 3 and all(v["tipo"] == "REGULAMENTO" for v in do_regulamento)
    assert len(pagina) == 2
    assert client.get(base(ed) + "/termos?tipo=NADA", headers=cab(org)).status_code == 422


def test_versao_de_outra_edicao_nao_e_encontrada(client, org, edicao):
    h1, h2 = edicao(), edicao()
    r = novo_rascunho(client, org, h1)

    assert publicar(client, org, h2, r).status_code == 404
    assert client.delete(base(h2) + f"/termos/{r['id']}", headers=cab(org)).status_code == 404


def test_publicacoes_simultaneas_deixam_uma_unica_vigente(client, org, ed):
    versoes = [novo_rascunho(client, org, ed, str(n)) for n in range(4)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        codigos = [
            f.result().status_code
            for f in [pool.submit(publicar, client, org, ed, v) for v in versoes]
        ]

    assert all(c in (200, 409) for c in codigos) and 200 in codigos
    vigentes = [
        v for v in client.get(base(ed) + "/termos", headers=cab(org)).json() if v["vigente"]
    ]
    assert len(vigentes) == 1


# --- Treinamento (RF35) ---


def sessao_corpo(**campos):
    return {"titulo": "Sessão 1", "inicio": iso(3), "local": "Auditório", **campos}


def nova_sessao(client, org, h, **campos):
    resposta = client.post(
        base(h) + "/treinamento/sessoes", json=sessao_corpo(**campos), headers=cab(org)
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@pytest.fixture
def equipe_aprovada(sql, org):
    """Equipe com resultado homologado em uma edição, com `aprovada` à escolha."""

    def criar(h: str, aprovada: bool = True) -> str:
        tema = sql(
            "INSERT INTO temas (hackathon_id, titulo, ativo)"
            " VALUES (:h, 'Tema', true) RETURNING id",
            h=h,
        )[0]["id"]
        equipe = sql(
            "INSERT INTO equipes (hackathon_id, nome, situacao)"
            " VALUES (:h, :n, 'HOMOLOGADA') RETURNING id",
            h=h,
            n=f"Equipe {uuid4().hex[:6]}",
        )[0]["id"]
        proposta = sql(
            "INSERT INTO submissoes (equipe_id, hackathon_id, tema_id, status, titulo, descricao,"
            " ods,"
            " bases_dados, enviado_em) VALUES (:e, :h, :t, 'ENVIADA', 'P', 'D', '{1}', 'B', now())"
            " RETURNING id",
            e=equipe,
            h=h,
            t=tema,
        )[0]["id"]
        hom = sql(
            "INSERT INTO homologacoes_resultado (hackathon_id, homologado_por, total_propostas,"
            " total_aprovadas) VALUES (:h, :u, 1, :a) RETURNING id",
            h=h,
            u=org["id"],
            a=1 if aprovada else 0,
        )[0]["id"]
        sql(
            "INSERT INTO resultados_proposta (homologacao_id, hackathon_id, submissao_id,"
            " equipe_id, nota_media, classificacao, avaliacoes, recomendacoes_aprovacao,"
            " recomendacoes_reprovacao, aprovada) VALUES (:hom, :h, :p, :e, 8, 1, 2, 2, 0, :ap)",
            hom=hom,
            h=h,
            p=proposta,
            e=equipe,
            ap=aprovada,
        )
        return str(equipe)

    return criar


@pytest.fixture
def integrante(sql, usuario_no_banco):
    def criar(h: str, equipe: str) -> dict:
        pessoa = usuario_no_banco(senha=None)
        sql(
            "INSERT INTO membros_equipe (equipe_id, hackathon_id, usuario_id, funcao)"
            " VALUES (:e, :h, :u, 'DESENVOLVEDOR')",
            e=equipe,
            h=h,
            u=pessoa["id"],
        )
        return pessoa

    return criar


def test_sessao_exige_data_e_local_ou_link(client, org, ed):
    caminho = base(ed) + "/treinamento/sessoes"

    sem_onde = client.post(caminho, json={"titulo": "S", "inicio": iso(1)}, headers=cab(org))
    so_link = client.post(
        caminho,
        json=sessao_corpo(local=None, link_url="https://meet.exemplo.com/abc"),
        headers=cab(org),
    )
    sem_data = client.post(caminho, json={"titulo": "S", "local": "L"}, headers=cab(org))
    fim_antes = client.post(caminho, json=sessao_corpo(fim=iso(2)), headers=cab(org))
    link_http = client.post(
        caminho, json=sessao_corpo(link_url="http://meet.exemplo.com"), headers=cab(org)
    )

    assert so_link.status_code == 201
    assert (
        sem_onde.status_code
        == sem_data.status_code
        == fim_antes.status_code
        == link_http.status_code
        == 422
    )


def test_materiais_sao_so_links(client, org, ed):
    sessao = nova_sessao(client, org, ed)
    caminho = base(ed) + f"/treinamento/sessoes/{sessao['id']}/materiais"

    bom = client.post(
        caminho,
        json={"titulo": "Slides", "url": "https://drive.exemplo.com/slides"},
        headers=cab(org),
    )
    ruins = [
        client.post(caminho, json={"titulo": "X", "url": url}, headers=cab(org))
        for url in ("http://x.com/a", "javascript:alert(1)", "https://u:p@x.com/a", "arquivo.pdf")
    ]
    sem_titulo = client.post(caminho, json={"url": LINK}, headers=cab(org))

    assert bom.status_code == 201 and bom.json()["ordem"] == 0
    assert all(r.status_code == 422 for r in ruins) and sem_titulo.status_code == 422


def test_materiais_na_ordem_e_remocao(client, org, ed):
    sessao = nova_sessao(client, org, ed)
    caminho = base(ed) + f"/treinamento/sessoes/{sessao['id']}/materiais"
    m1 = client.post(caminho, json={"titulo": "Um", "url": LINK}, headers=cab(org)).json()
    m2 = client.post(caminho, json={"titulo": "Dois", "url": LINK}, headers=cab(org)).json()

    listada = client.get(base(ed) + "/treinamento/sessoes", headers=cab(org)).json()[0]
    assert [m["titulo"] for m in listada["materiais"]] == ["Um", "Dois"]
    assert (m1["ordem"], m2["ordem"]) == (0, 1)
    assert client.delete(f"{caminho}/{m1['id']}", headers=cab(org)).status_code == 204
    assert client.delete(f"{caminho}/{m1['id']}", headers=cab(org)).status_code == 404
    assert [
        m["titulo"]
        for m in client.get(base(ed) + "/treinamento/sessoes", headers=cab(org)).json()[0][
            "materiais"
        ]
    ] == ["Dois"]


def test_materiais_simultaneos_recebem_posicoes_distintas(client, org, ed):
    sessao = nova_sessao(client, org, ed)
    caminho = base(ed) + f"/treinamento/sessoes/{sessao['id']}/materiais"

    with ThreadPoolExecutor(max_workers=5) as pool:
        futuros = [
            pool.submit(
                client.post, caminho, json={"titulo": f"M{n}", "url": LINK}, headers=cab(org)
            )
            for n in range(5)
        ]
        assert [f.result().status_code for f in futuros] == [201] * 5

    ordens = [
        m["ordem"]
        for m in client.get(base(ed) + "/treinamento/sessoes", headers=cab(org)).json()[0][
            "materiais"
        ]
    ]
    assert sorted(ordens) == [0, 1, 2, 3, 4]


def test_editar_sessao_valida_o_resultado_final(client, org, ed):
    sessao = nova_sessao(client, org, ed, local="Auditório", link_url=None, fim=iso(4))
    caminho = base(ed) + f"/treinamento/sessoes/{sessao['id']}"

    sem_onde = client.patch(caminho, json={"local": None}, headers=cab(org))
    fim_antes = client.patch(caminho, json={"inicio": iso(9)}, headers=cab(org))
    certo = client.patch(
        caminho,
        json={
            "local": None,
            "link_url": "https://meet.exemplo.com/x",
            "fim": None,
            "publicado": True,
        },
        headers=cab(org),
    )

    assert sem_onde.status_code == fim_antes.status_code == 422
    assert certo.status_code == 200
    assert (certo.json()["local"], certo.json()["fim"], certo.json()["publicado"]) == (
        None,
        None,
        True,
    )


def test_excluir_sessao_leva_os_materiais(client, org, sql, ed):
    sessao = nova_sessao(client, org, ed)
    client.post(
        base(ed) + f"/treinamento/sessoes/{sessao['id']}/materiais",
        json={"titulo": "M", "url": LINK},
        headers=cab(org),
    )

    assert (
        client.delete(
            base(ed) + f"/treinamento/sessoes/{sessao['id']}", headers=cab(org)
        ).status_code
        == 204
    )

    assert sql("SELECT 1 FROM materiais_treinamento WHERE sessao_id = :s", s=sessao["id"]) == []
    assert (
        client.delete(
            base(ed) + f"/treinamento/sessoes/{sessao['id']}", headers=cab(org)
        ).status_code
        == 404
    )


def test_listar_sessoes_filtra_e_pagina(client, org, ed):
    for n in range(3):
        nova_sessao(client, org, ed, titulo=f"S{n}", inicio=iso(n + 1), publicado=n == 0)

    publicadas = client.get(
        base(ed) + "/treinamento/sessoes?publicado=true", headers=cab(org)
    ).json()
    pagina = client.get(
        base(ed) + "/treinamento/sessoes?limite=1&deslocamento=2", headers=cab(org)
    ).json()

    assert [s["titulo"] for s in publicadas] == ["S0"]
    assert [s["titulo"] for s in pagina] == ["S2"]


def test_equipe_aprovada_ve_so_o_publicado(client, org, ed, equipe_aprovada, integrante):
    equipe = equipe_aprovada(ed)
    pessoa = integrante(ed, equipe)
    publicada = nova_sessao(client, org, ed, titulo="Pública", inicio=iso(2), publicado=True)
    nova_sessao(client, org, ed, titulo="Rascunho", inicio=iso(1))
    client.post(
        base(ed) + f"/treinamento/sessoes/{publicada['id']}/materiais",
        json={"titulo": "Slides", "url": LINK},
        headers=cab(org),
    )

    resposta = client.get(f"/hackathons/{ed}/treinamento", headers=cab(pessoa))

    assert resposta.status_code == 200
    [sessao] = resposta.json()
    assert sessao["titulo"] == "Pública"
    assert [m["titulo"] for m in sessao["materiais"]] == ["Slides"]


def test_equipe_nao_aprovada_nao_ve(client, org, ed, equipe_aprovada, integrante):
    equipe = equipe_aprovada(ed, aprovada=False)
    pessoa = integrante(ed, equipe)
    nova_sessao(client, org, ed, publicado=True)

    resposta = client.get(f"/hackathons/{ed}/treinamento", headers=cab(pessoa))

    assert resposta.status_code == 403
    assert "Auditório" not in resposta.text


def test_quem_nao_tem_equipe_nao_ve(client, org, ed, usuario_no_banco):
    nova_sessao(client, org, ed, publicado=True)
    participante = usuario_no_banco(senha=None)
    mentor = usuario_no_banco(papel="MENTOR", senha=None)
    tecnico = usuario_no_banco(papel="COMITE_TECNICO", senha=None)

    for pessoa in (participante, mentor, tecnico):
        assert client.get(f"/hackathons/{ed}/treinamento", headers=cab(pessoa)).status_code == 403


def test_aprovada_em_outra_edicao_nao_vale(client, org, edicao, equipe_aprovada, integrante):
    h1, h2 = edicao(), edicao()
    pessoa = integrante(h1, equipe_aprovada(h1))
    nova_sessao(client, org, h2, publicado=True)

    assert client.get(f"/hackathons/{h2}/treinamento", headers=cab(pessoa)).status_code == 403
    assert client.get(f"/hackathons/{h1}/treinamento", headers=cab(pessoa)).status_code == 200


@pytest.mark.parametrize("papel", ["ORGANIZADOR", "COMITE_CIENTIFICO", "DEV"])
def test_organizacao_ve_o_treinamento(client, org, ed, usuario_no_banco, papel):
    nova_sessao(client, org, ed, publicado=True)
    pessoa = usuario_no_banco(papel=papel, senha=None)

    assert len(client.get(f"/hackathons/{ed}/treinamento", headers=cab(pessoa)).json()) == 1


def test_treinamento_sem_login_conta_pendente_e_edicao_inexistente(client, ed, usuario_no_banco):
    pendente = usuario_no_banco(senha=None, situacao_conta="PENDENTE")

    assert client.get(f"/hackathons/{ed}/treinamento").status_code == 401
    assert client.get(f"/hackathons/{ed}/treinamento", headers=cab(pendente)).status_code == 403
    assert (
        client.get(f"/hackathons/{uuid4()}/treinamento", headers=cab(pendente)).status_code == 403
    )
    org_ = usuario_no_banco(papel="ORGANIZADOR", senha=None)
    assert client.get(f"/hackathons/{uuid4()}/treinamento", headers=cab(org_)).status_code == 404


def test_sessoes_em_ordem_cronologica(client, org, ed):
    for titulo, dias in (("C", 9), ("A", 1), ("B", 5)):
        nova_sessao(client, org, ed, titulo=titulo, inicio=iso(dias), publicado=True)

    titulos = [
        s["titulo"] for s in client.get(f"/hackathons/{ed}/treinamento", headers=cab(org)).json()
    ]

    assert titulos == ["A", "B", "C"]


# --- Integridade e documentação ---


def test_edicao_com_conteudo_nao_pode_ser_excluida(client, org, ed):
    novo_apoiador(client, org, ed)

    resposta = client.delete(f"/admin/hackathons/{ed}", headers=cab(org))

    assert resposta.status_code == 409


def test_swagger_documenta_todas_as_rotas_novas():
    from app.main import app

    esquema = app.openapi()
    prefixos = (
        "/publico/hackathons",
        "/apoiadores",
        "/faq",
        "/cronograma",
        "/termos",
        "/treinamento",
    )
    operacoes = [
        (caminho, metodo, op)
        for caminho, ops in esquema["paths"].items()
        if any(p in caminho for p in prefixos)
        for metodo, op in ops.items()
    ]
    assert len(operacoes) >= 30
    for caminho, metodo, op in operacoes:
        assert op.get("summary"), f"{metodo} {caminho} sem resumo"
        assert op.get("responses"), f"{metodo} {caminho} sem respostas"
    admin = [
        (c, m, op) for c, m, op in operacoes if c.startswith("/admin/hackathons/{hackathon_id}/")
    ]
    for caminho, metodo, op in admin:
        if (caminho, metodo) in {
            ("/admin/hackathons/{hackathon_id}/treinamento", "get"),
            ("/admin/hackathons/{hackathon_id}/treinamento/concluir", "post"),
        }:
            continue
        assert op.get("description"), f"{metodo} {caminho} sem descrição"
        assert {"401", "403"} <= set(op["responses"]), f"{metodo} {caminho} sem 401/403"
