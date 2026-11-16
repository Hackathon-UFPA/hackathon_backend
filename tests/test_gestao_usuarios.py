"""
Gestão administrativa de usuários (BE-S5-07, RN24): listar, consultar, editar, desativar e
reativar, com a hierarquia de perfis, proteção contra escalada de privilégio e contra ficar sem
Organizador.

Estes testes gravam no banco de verdade; as fixtures de conftest.py apagam os dados no final.
"""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from app.security.token import criar_token
from tests.conftest import SENHA_PADRAO

BASE = "/admin/usuarios"


def cabecalho_de(usuario: dict) -> dict:
    return {"Authorization": f"Bearer {criar_token(usuario['id'])}"}


def entrar(client, email: str, senha: str = SENHA_PADRAO):
    return client.post("/auth/login", json={"email": email, "senha": senha})


def linha(sql, usuario_id) -> dict:
    return sql("SELECT * FROM usuarios WHERE id = :id", id=usuario_id)[0]


@pytest.fixture
def conta(usuario_no_banco, sql):
    """Cria um usuário com nome, para os testes de busca e edição."""

    def criar(papel: str = "PARTICIPANTE", nome: str | None = None, **opcoes) -> dict:
        usuario = usuario_no_banco(papel=papel, **opcoes)
        nome = nome or f"Pessoa {uuid4().hex[:8]}"
        sql("UPDATE usuarios SET nome = :n WHERE id = :id", n=nome, id=usuario["id"])
        return {**usuario, "nome": nome}

    return criar


@pytest.fixture
def organizador(conta):
    return conta("ORGANIZADOR")


@pytest.fixture
def cientifico(conta):
    return conta("COMITE_CIENTIFICO")


@pytest.fixture
def unico_organizador(sql, organizador):
    """Deixa `organizador` como o único Organizador ativo do banco e restaura o resto no final."""
    outros = [
        linha_["id"]
        for linha_ in sql(
            "SELECT id FROM usuarios WHERE papel = 'ORGANIZADOR' AND ativo AND id <> :id",
            id=organizador["id"],
        )
    ]
    if outros:
        sql("UPDATE usuarios SET ativo = false WHERE id = ANY(:ids)", ids=outros)
    yield organizador
    if outros:
        sql("UPDATE usuarios SET ativo = true WHERE id = ANY(:ids)", ids=outros)


# --- Quem pode usar as rotas (RN24) ---


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO"])
def test_perfis_sem_gestao_recebem_403_em_todas_as_rotas(client, conta, papel):
    quem = conta(papel)
    alvo = conta("COMITE_TECNICO")
    caminho = f"{BASE}/{alvo['id']}"
    cab = cabecalho_de(quem)

    assert client.get(BASE, headers=cab).status_code == 403
    assert client.get(caminho, headers=cab).status_code == 403
    assert client.patch(caminho, json={"nome": "X"}, headers=cab).status_code == 403
    assert client.post(f"{caminho}/desativar", headers=cab).status_code == 403
    assert client.post(f"{caminho}/reativar", headers=cab).status_code == 403


def test_conta_pendente_nao_gerencia(client, conta):
    quem = conta("ORGANIZADOR", situacao_conta="PENDENTE")

    assert client.get(BASE, headers=cabecalho_de(quem)).status_code == 403


def test_sem_token_recebe_401(client, conta):
    alvo = conta()

    assert client.get(BASE).status_code == 401
    assert client.get(f"{BASE}/{alvo['id']}").status_code == 401
    assert client.patch(f"{BASE}/{alvo['id']}", json={"nome": "X"}).status_code == 401
    assert client.post(f"{BASE}/{alvo['id']}/desativar").status_code == 401
    assert client.post(f"{BASE}/{alvo['id']}/reativar").status_code == 401


def test_comite_cientifico_so_alcanca_comite_tecnico_e_mentor(client, conta, cientifico):
    cab = cabecalho_de(cientifico)
    for papel in ("PARTICIPANTE", "COMITE_CIENTIFICO", "ORGANIZADOR", "DEV"):
        alvo = conta(papel)
        caminho = f"{BASE}/{alvo['id']}"
        assert client.get(caminho, headers=cab).status_code == 403, papel
        assert client.patch(caminho, json={"nome": "X"}, headers=cab).status_code == 403, papel
        assert client.post(f"{caminho}/desativar", headers=cab).status_code == 403, papel
        assert client.post(f"{caminho}/reativar", headers=cab).status_code == 403, papel
    tecnico = conta("COMITE_TECNICO")
    assert client.get(f"{BASE}/{tecnico['id']}", headers=cab).status_code == 200


def test_organizador_nao_alcanca_dev(client, conta, organizador):
    dev = conta("DEV")

    cab = cabecalho_de(organizador)
    assert client.get(f"{BASE}/{dev['id']}", headers=cab).status_code == 403
    assert client.post(f"{BASE}/{dev['id']}/desativar", headers=cab).status_code == 403


def test_dev_alcanca_todos(client, conta):
    dev = conta("DEV")
    alvo = conta("ORGANIZADOR")

    assert client.get(f"{BASE}/{alvo['id']}", headers=cabecalho_de(dev)).status_code == 200


# --- Listar e consultar ---


def test_organizador_lista_menos_dev(client, conta, organizador):
    participante = conta("PARTICIPANTE")
    dev = conta("DEV")

    resposta = client.get(BASE, params={"limite": 100}, headers=cabecalho_de(organizador))

    assert resposta.status_code == 200
    ids = {u["id"] for u in resposta.json()}
    assert str(participante["id"]) in ids
    assert str(dev["id"]) not in ids
    assert all(u["papel"] != "DEV" for u in resposta.json())


def test_comite_cientifico_lista_so_o_que_gerencia(client, conta, cientifico):
    tecnico = conta("COMITE_TECNICO")
    participante = conta("PARTICIPANTE")

    resposta = client.get(BASE, params={"limite": 100}, headers=cabecalho_de(cientifico))

    ids = {u["id"] for u in resposta.json()}
    assert str(tecnico["id"]) in ids
    assert str(participante["id"]) not in ids
    assert {u["papel"] for u in resposta.json()} <= {"COMITE_TECNICO", "MENTOR"}


def test_filtrar_perfil_fora_do_alcance_devolve_lista_vazia(client, conta, cientifico):
    conta("ORGANIZADOR")

    resposta = client.get(BASE, params={"papel": "ORGANIZADOR"}, headers=cabecalho_de(cientifico))

    assert resposta.status_code == 200
    assert resposta.json() == []


def test_filtros_de_busca_e_situacao(client, conta, organizador, sql):
    marca = uuid4().hex[:10]
    ativo = conta("COMITE_TECNICO", nome=f"Ana {marca}")
    inativo = conta("COMITE_TECNICO", nome=f"Bia {marca}", ativo=False)
    cab = cabecalho_de(organizador)

    por_nome = client.get(BASE, params={"busca": marca.upper()}, headers=cab).json()
    so_ativos = client.get(BASE, params={"busca": marca, "ativo": True}, headers=cab).json()
    so_inativos = client.get(BASE, params={"busca": marca, "ativo": False}, headers=cab).json()
    por_email = client.get(BASE, params={"busca": ativo["email"]}, headers=cab).json()

    assert {u["id"] for u in por_nome} == {str(ativo["id"]), str(inativo["id"])}
    assert [u["id"] for u in so_ativos] == [str(ativo["id"])]
    assert [u["id"] for u in so_inativos] == [str(inativo["id"])]
    assert [u["id"] for u in por_email] == [str(ativo["id"])]


def test_paginacao_e_parametros_invalidos(client, conta, organizador):
    marca = uuid4().hex[:10]
    for letra in "abc":
        conta("COMITE_TECNICO", nome=f"{letra} {marca}")
    cab = cabecalho_de(organizador)

    pagina = client.get(BASE, params={"busca": marca, "limite": 2}, headers=cab).json()
    resto = client.get(BASE, params={"busca": marca, "limite": 2, "deslocamento": 2}, headers=cab)

    assert len(pagina) == 2
    assert len(resto.json()) == 1
    assert client.get(BASE, params={"limite": 0}, headers=cab).status_code == 422
    assert client.get(BASE, params={"limite": 101}, headers=cab).status_code == 422
    assert client.get(BASE, params={"deslocamento": -1}, headers=cab).status_code == 422
    assert client.get(BASE, params={"papel": "NADA"}, headers=cab).status_code == 422


def test_resposta_nao_traz_senha_nem_versao_de_sessao(client, conta, organizador):
    alvo = conta("COMITE_TECNICO")

    corpo = client.get(f"{BASE}/{alvo['id']}", headers=cabecalho_de(organizador)).json()

    assert "senha_hash" not in corpo
    assert "versao_sessao" not in corpo
    assert corpo["email"] == alvo["email"]


def test_consultar_inexistente_e_id_invalido(client, organizador):
    cab = cabecalho_de(organizador)

    assert client.get(f"{BASE}/{uuid4()}", headers=cab).status_code == 404
    assert client.get(f"{BASE}/nao-e-uuid", headers=cab).status_code == 422


# --- Editar ---


def test_editar_dados_pessoais(client, sql, conta, cientifico):
    alvo = conta("COMITE_TECNICO")

    resposta = client.patch(
        f"{BASE}/{alvo['id']}",
        json={"nome": "  Novo Nome ", "curso": "Matemática", "periodo": 3},
        headers=cabecalho_de(cientifico),
    )

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Novo Nome"
    dados = linha(sql, alvo["id"])
    assert (dados["nome"], dados["curso"], dados["periodo"]) == ("Novo Nome", "Matemática", 3)
    assert dados["email"] == alvo["email"]
    assert dados["atualizado_em"] is not None


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("email", "outro@testes.com"),
        ("ativo", False),
        ("situacao_conta", "ATIVA"),
        ("max_equipes", 3),
        ("senha", "novasenha123"),
        ("senha_hash", "x"),
        ("versao_sessao", 5),
    ],
)
def test_editar_recusa_campos_fora_da_lista(client, sql, conta, organizador, campo, valor):
    alvo = conta("COMITE_TECNICO")
    antes = linha(sql, alvo["id"])

    resposta = client.patch(
        f"{BASE}/{alvo['id']}", json={campo: valor}, headers=cabecalho_de(organizador)
    )

    assert resposta.status_code == 422
    assert linha(sql, alvo["id"]) == antes


def test_editar_recusa_nulos(client, conta, organizador):
    alvo = conta("COMITE_TECNICO")

    resposta = client.patch(
        f"{BASE}/{alvo['id']}", json={"papel": None}, headers=cabecalho_de(organizador)
    )

    assert resposta.status_code == 422


def test_editar_inexistente(client, organizador):
    resposta = client.patch(
        f"{BASE}/{uuid4()}", json={"nome": "X"}, headers=cabecalho_de(organizador)
    )

    assert resposta.status_code == 404


def test_organizador_troca_perfil_entre_os_de_gestao(client, sql, conta, organizador):
    alvo = conta("COMITE_TECNICO")
    cab = cabecalho_de(organizador)

    resposta = client.patch(
        f"{BASE}/{alvo['id']}", json={"papel": "COMITE_CIENTIFICO"}, headers=cab
    )

    assert resposta.status_code == 200
    assert resposta.json()["papel"] == "COMITE_CIENTIFICO"
    assert linha(sql, alvo["id"])["papel"] == "COMITE_CIENTIFICO"
    # o perfil novo vale já no próximo pedido, porque o token não carrega o papel
    assert client.get(BASE, headers=cabecalho_de(alvo)).status_code == 200


@pytest.mark.parametrize(
    "de, para",
    [
        ("COMITE_TECNICO", "PARTICIPANTE"),
        ("COMITE_TECNICO", "MENTOR"),
        ("COMITE_TECNICO", "DEV"),
        ("PARTICIPANTE", "COMITE_TECNICO"),
        ("PARTICIPANTE", "ORGANIZADOR"),
    ],
)
def test_troca_de_perfil_fora_do_conjunto_permitido(client, sql, conta, organizador, de, para):
    alvo = conta(de)

    resposta = client.patch(
        f"{BASE}/{alvo['id']}", json={"papel": para}, headers=cabecalho_de(organizador)
    )

    # DEV está fora do alcance do Organizador (403); os demais, fora da troca (409)
    assert resposta.status_code == (403 if para == "DEV" else 409)
    assert linha(sql, alvo["id"])["papel"] == de


def test_comite_cientifico_nao_promove_ninguem(client, sql, conta, cientifico):
    """Escalada de privilégio: quem gerencia não entrega um perfil acima do próprio alcance."""
    alvo = conta("COMITE_TECNICO")
    cab = cabecalho_de(cientifico)

    for papel in ("ORGANIZADOR", "COMITE_CIENTIFICO", "DEV"):
        resposta = client.patch(f"{BASE}/{alvo['id']}", json={"papel": papel}, headers=cab)
        assert resposta.status_code == 403, papel
    assert linha(sql, alvo["id"])["papel"] == "COMITE_TECNICO"


def test_ninguem_altera_o_proprio_perfil(client, sql, organizador):
    resposta = client.patch(
        f"{BASE}/{organizador['id']}",
        json={"papel": "COMITE_TECNICO"},
        headers=cabecalho_de(organizador),
    )

    assert resposta.status_code == 409
    assert linha(sql, organizador["id"])["papel"] == "ORGANIZADOR"


def test_editar_o_proprio_nome_pela_rota_admin_e_permitido(client, organizador):
    resposta = client.patch(
        f"{BASE}/{organizador['id']}", json={"nome": "Meu Nome"}, headers=cabecalho_de(organizador)
    )

    assert resposta.status_code == 200


def test_rebaixar_o_ultimo_organizador_e_recusado(client, sql, conta, unico_organizador):
    """Quem rebaixa precisa ser DEV (um Organizador não altera o próprio perfil)."""
    dev = conta("DEV")

    resposta = client.patch(
        f"{BASE}/{unico_organizador['id']}",
        json={"papel": "COMITE_TECNICO"},
        headers=cabecalho_de(dev),
    )

    assert resposta.status_code == 409
    assert linha(sql, unico_organizador["id"])["papel"] == "ORGANIZADOR"


def test_mentor_nao_se_edita_por_aqui(client, sql, conta, cientifico):
    mentor = conta("MENTOR")

    resposta = client.patch(
        f"{BASE}/{mentor['id']}", json={"nome": "Outro"}, headers=cabecalho_de(cientifico)
    )

    assert resposta.status_code == 409
    assert linha(sql, mentor["id"])["nome"] == mentor["nome"]


# --- Desativar e reativar ---


def test_desativar_bloqueia_o_acesso_na_hora(client, sql, conta, organizador):
    alvo = conta("COMITE_TECNICO")
    sessao = entrar(client, alvo["email"]).json()["access_token"]
    cab_alvo = {"Authorization": f"Bearer {sessao}"}
    assert client.get("/me", headers=cab_alvo).status_code == 200

    resposta = client.post(f"{BASE}/{alvo['id']}/desativar", headers=cabecalho_de(organizador))

    assert resposta.status_code == 200
    assert resposta.json()["ativo"] is False
    assert client.get("/me", headers=cab_alvo).status_code == 401
    assert entrar(client, alvo["email"]).status_code == 401
    assert linha(sql, alvo["id"])["versao_sessao"] == 1


def test_desativar_gasta_links_pendentes(client, sql, conta, organizador):
    alvo = conta("COMITE_TECNICO")
    client.post("/auth/recuperar-senha", json={"email": alvo["email"]})
    assert sql("SELECT 1 FROM tokens_usuario WHERE usuario_id = :u", u=alvo["id"])

    client.post(f"{BASE}/{alvo['id']}/desativar", headers=cabecalho_de(organizador))

    abertos = sql(
        "SELECT 1 FROM tokens_usuario WHERE usuario_id = :u AND utilizado_em IS NULL",
        u=alvo["id"],
    )
    assert abertos == []


def test_desativar_duas_vezes_nao_muda_nada(client, conta, organizador):
    alvo = conta("COMITE_TECNICO")
    cab = cabecalho_de(organizador)

    primeira = client.post(f"{BASE}/{alvo['id']}/desativar", headers=cab)
    segunda = client.post(f"{BASE}/{alvo['id']}/desativar", headers=cab)

    assert primeira.status_code == segunda.status_code == 200
    assert segunda.json()["ativo"] is False


def test_desativar_a_propria_conta(client, sql, conta, organizador):
    outro = conta("ORGANIZADOR")  # garante que não é o último
    resposta = client.post(
        f"{BASE}/{organizador['id']}/desativar", headers=cabecalho_de(organizador)
    )

    assert resposta.status_code == 409
    assert linha(sql, organizador["id"])["ativo"] is True
    assert linha(sql, outro["id"])["ativo"] is True


def test_desativar_inexistente(client, organizador):
    assert (
        client.post(f"{BASE}/{uuid4()}/desativar", headers=cabecalho_de(organizador)).status_code
        == 404
    )


def test_desativar_o_ultimo_organizador_ativo(client, sql, conta, unico_organizador):
    dev = conta("DEV")

    resposta = client.post(f"{BASE}/{unico_organizador['id']}/desativar", headers=cabecalho_de(dev))

    assert resposta.status_code == 409
    assert linha(sql, unico_organizador["id"])["ativo"] is True


def test_desativar_organizador_havendo_outro_ativo(client, sql, conta, organizador):
    outro = conta("ORGANIZADOR")

    resposta = client.post(f"{BASE}/{outro['id']}/desativar", headers=cabecalho_de(organizador))

    assert resposta.status_code == 200
    assert linha(sql, outro["id"])["ativo"] is False


def test_mentor_nao_se_desativa_nem_reativa_por_aqui(client, sql, conta, cientifico):
    mentor = conta("MENTOR")
    cab = cabecalho_de(cientifico)

    assert client.post(f"{BASE}/{mentor['id']}/desativar", headers=cab).status_code == 409
    assert client.post(f"{BASE}/{mentor['id']}/reativar", headers=cab).status_code == 409
    assert linha(sql, mentor["id"])["ativo"] is True


def test_reativar_devolve_o_acesso(client, conta, organizador):
    alvo = conta("COMITE_TECNICO", ativo=False)
    assert entrar(client, alvo["email"]).status_code == 401

    resposta = client.post(f"{BASE}/{alvo['id']}/reativar", headers=cabecalho_de(organizador))

    assert resposta.status_code == 200
    assert resposta.json()["ativo"] is True
    assert entrar(client, alvo["email"]).status_code == 200


def test_reativar_conta_ativa_nao_muda_nada(client, conta, organizador):
    alvo = conta("COMITE_TECNICO")

    resposta = client.post(f"{BASE}/{alvo['id']}/reativar", headers=cabecalho_de(organizador))

    assert resposta.status_code == 200
    assert resposta.json()["ativo"] is True


def test_conta_desativada_nao_gerencia(client, sql, conta, organizador):
    outro = conta("ORGANIZADOR")
    alvo = conta("COMITE_TECNICO")
    client.post(f"{BASE}/{outro['id']}/desativar", headers=cabecalho_de(organizador))

    assert client.get(BASE, headers=cabecalho_de(outro)).status_code == 401
    assert (
        client.post(f"{BASE}/{alvo['id']}/desativar", headers=cabecalho_de(outro)).status_code
        == 401
    )


def test_desativacoes_cruzadas_dos_dois_ultimos_organizadores(
    client, sql, conta, unico_organizador
):
    """A e B são os únicos Organizadores ativos e se desativam ao mesmo tempo: só uma passa."""
    a = unico_organizador
    b = conta("ORGANIZADOR")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [
            pool.submit(client.post, f"{BASE}/{b['id']}/desativar", headers=cabecalho_de(a)),
            pool.submit(client.post, f"{BASE}/{a['id']}/desativar", headers=cabecalho_de(b)),
        ]
        codigos = sorted(f.result().status_code for f in futuros)

    assert codigos.count(200) == 1
    assert codigos[0] == 200 and codigos[1] in (401, 409)
    ativos = sql(
        "SELECT count(*) AS n FROM usuarios WHERE id = ANY(:ids) AND ativo",
        ids=[a["id"], b["id"]],
    )[0]["n"]
    assert ativos == 1


# --- Quem o usuário comum nunca consegue ser (escalada pela própria conta) ---


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO", "COMITE_CIENTIFICO"])
def test_ninguem_se_promove_pela_rota_do_proprio_perfil(client, sql, conta, papel):
    quem = conta(papel)

    for campo, valor in (("papel", "ORGANIZADOR"), ("papel", "DEV")):
        resposta = client.patch("/me", json={campo: valor}, headers=cabecalho_de(quem))
        assert resposta.status_code == 422
    assert linha(sql, quem["id"])["papel"] == papel
