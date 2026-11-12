"""RF37, RN24 e RN33: API, persistência, convite, termos e integração com o outbox."""

import asyncio
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings
from app.integrations.email import ProvedorMemoria
from app.security.senha import senha_confere
from app.security.token import criar_token
from app.services.mentor import validar_elegibilidade

SENHA = "MinhaSenha123"
PERFIL = {"nome": "Maria da Silva", "empresa_parceira": "Açaí Valley", "area_atuacao": "Dados"}


def headers(usuario):
    return {"Authorization": f"Bearer {criar_token(usuario['id'])}"}


@pytest.fixture
def gestor(usuario_no_banco):
    return usuario_no_banco(papel="COMITE_CIENTIFICO")


@pytest.fixture
def criar_mentor(client, gestor, novo_email):
    def criar(**extras):
        resposta = client.post(
            "/admin/mentores",
            headers=headers(gestor),
            json={**PERFIL, "email": novo_email(), "max_equipes": 2, **extras},
        )
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    return criar


@pytest.fixture
def termos_mentor(sql, hackathon_aberto, novo_email):
    ids = []
    for tipo in ("REGULAMENTO", "TERMO_CONSENTIMENTO"):
        ids.append(
            str(
                sql(
                    "INSERT INTO termos (hackathon_id, tipo, versao, titulo, conteudo, vigente)"
                    " VALUES (:h, CAST(:t AS tipo_termo), '1', 'Leia', 'Conteúdo', true)"
                    " RETURNING id",
                    h=hackathon_aberto,
                    t=tipo,
                )[0]["id"]
            )
        )
    yield {"hackathon_id": str(hackathon_aberto), "termos_ids": ids}
    sql(
        "DELETE FROM aceites_termos WHERE termo_id IN"
        " (SELECT id FROM termos WHERE hackathon_id=:h)",
        h=hackathon_aberto,
    )
    sql("DELETE FROM termos WHERE hackathon_id=:h", h=hackathon_aberto)


def token_do_email(sql, mentor):
    corpo = sql(
        "SELECT corpo_texto FROM emails_outbox WHERE usuario_id=:u ORDER BY criado_em DESC, id",
        u=UUID(mentor["id"]),
    )[0]["corpo_texto"]
    return re.search(r"#token=([\w-]+)", corpo).group(1)


def ativar(client, sql, mentor, termos, **extras):
    return client.post(
        "/mentores/ativacao",
        json={**PERFIL, **termos, "token": token_do_email(sql, mentor), "senha": SENHA, **extras},
    )


def estado(sql, mentor):
    return sql("SELECT * FROM usuarios WHERE id=:u", u=UUID(mentor["id"]))[0]


@pytest.mark.parametrize("papel", ["COMITE_CIENTIFICO", "ORGANIZADOR", "DEV"])
def test_cadastro_por_perfis_autorizados(client, sql, usuario_no_banco, novo_email, papel):
    usuario = usuario_no_banco(papel=papel)
    email = novo_email()
    resposta = client.post(
        "/admin/mentores",
        headers=headers(usuario),
        json={**PERFIL, "email": email.upper(), "max_equipes": 2},
    )
    assert resposta.status_code == 201
    mentor = resposta.json()
    assert mentor["email"] == email.lower()
    assert mentor["papel"] == "MENTOR"
    assert mentor["ativo"] is False
    assert mentor["situacao_conta"] == "ATIVA"  # RN25 não representa a RN33.
    assert mentor["mentor_ativado_em"] is None
    assert mentor["mentor_perfil_concluido_em"] is None
    assert estado(sql, mentor)["senha_hash"] is None
    assert sql("SELECT 1 FROM comprovantes_vinculo WHERE usuario_id=:u", u=UUID(mentor["id"])) == []
    assert "senha" not in resposta.text and "token" not in resposta.text


@pytest.mark.parametrize(
    "campo", ["nome", "email", "empresa_parceira", "area_atuacao", "max_equipes"]
)
def test_campos_obrigatorios(client, gestor, novo_email, campo):
    dados = {**PERFIL, "email": novo_email(), "max_equipes": 2}
    del dados[campo]
    assert client.post("/admin/mentores", headers=headers(gestor), json=dados).status_code == 422


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("nome", " "),
        ("empresa_parceira", ""),
        ("area_atuacao", "\t"),
        ("email", "invalido"),
        ("max_equipes", 0),
        ("max_equipes", -1),
        ("max_equipes", 1.5),
        ("max_equipes", True),
        ("max_equipes", "2"),
        ("max_equipes", 32768),
        ("max_equipes", None),
        ("nome", "a" * 256),
    ],
)
def test_campos_invalidos(client, gestor, novo_email, campo, valor):
    dados = {**PERFIL, "email": novo_email(), "max_equipes": 2, campo: valor}
    assert client.post("/admin/mentores", headers=headers(gestor), json=dados).status_code == 422


def test_email_duplicado_entre_perfis(client, gestor, usuario_no_banco, sql):
    participante = usuario_no_banco()
    antes = sql("SELECT count(*) AS n FROM emails_outbox")[0]["n"]
    resposta = client.post(
        "/admin/mentores",
        headers=headers(gestor),
        json={**PERFIL, "email": participante["email"].upper(), "max_equipes": 2},
    )
    assert resposta.status_code == 409
    assert sql("SELECT count(*) AS n FROM emails_outbox")[0]["n"] == antes


OPERACOES = [
    ("post", "/admin/mentores", {**PERFIL, "email": "novo@example.com", "max_equipes": 2}),
    ("get", "/admin/mentores", None),
    ("get", "/admin/mentores/{id}", None),
    ("patch", "/admin/mentores/{id}", {"nome": "Novo Nome"}),
    ("post", "/admin/mentores/{id}/convite", None),
    ("post", "/admin/mentores/{id}/ativar", {"hackathon_id": str(uuid4())}),
    ("post", "/admin/mentores/{id}/desativar", None),
]


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO"])
@pytest.mark.parametrize(("metodo", "caminho", "dados"), OPERACOES)
def test_perfis_proibidos(client, usuario_no_banco, papel, metodo, caminho, dados):
    usuario = usuario_no_banco(papel=papel)
    resposta = client.request(
        metodo,
        caminho.format(id=uuid4()),
        headers=headers(usuario),
        json=dados,
    )
    assert resposta.status_code == 403


@pytest.mark.parametrize(("metodo", "caminho", "dados"), OPERACOES)
def test_admin_sem_token(client, metodo, caminho, dados):
    assert client.request(metodo, caminho.format(id=uuid4()), json=dados).status_code == 401


def test_gestor_pendente_nao_cadastra(client, usuario_no_banco, novo_email):
    gestor = usuario_no_banco(papel="ORGANIZADOR", situacao_conta="PENDENTE")
    assert (
        client.post(
            "/admin/mentores",
            headers=headers(gestor),
            json={**PERFIL, "email": novo_email(), "max_equipes": 2},
        ).status_code
        == 403
    )


def test_listar_consultar_editar(client, gestor, criar_mentor, usuario_no_banco):
    mentor = criar_mentor()
    usuario_no_banco(papel="PARTICIPANTE")
    cabecalho = headers(gestor)
    lista = client.get("/admin/mentores?ativo=false&limite=100", headers=cabecalho).json()
    assert mentor["id"] in {item["id"] for item in lista}
    assert all(item["papel"] == "MENTOR" and not item["ativo"] for item in lista)
    url = f"/admin/mentores/{mentor['id']}"
    assert client.get(url, headers=cabecalho).json() == mentor
    resposta = client.patch(url, headers=cabecalho, json={"max_equipes": 4, "nome": "Novo Nome"})
    assert resposta.status_code == 200
    assert resposta.json()["max_equipes"] == 4
    assert resposta.json()["nome"] == "Novo Nome"
    assert resposta.json()["empresa_parceira"] == PERFIL["empresa_parceira"]
    assert not resposta.json()["ativo"]


@pytest.mark.parametrize(
    "dados",
    [
        {"nome": None},
        {"max_equipes": 0},
        {"ativo": True},
        {"papel": "DEV"},
        {"max_equipes": True},
        {"senha": SENHA},
    ],
)
def test_edicao_nao_contorna_validacoes(client, gestor, criar_mentor, dados):
    mentor = criar_mentor()
    assert (
        client.patch(
            f"/admin/mentores/{mentor['id']}",
            headers=headers(gestor),
            json=dados,
        ).status_code
        == 422
    )


def test_edicao_email_duplicado(client, gestor, criar_mentor, usuario_no_banco):
    mentor = criar_mentor()
    outro = usuario_no_banco()
    assert (
        client.patch(
            f"/admin/mentores/{mentor['id']}",
            headers=headers(gestor),
            json={"email": outro["email"].upper()},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "COMITE_TECNICO"])
def test_consulta_nao_confunde_outro_perfil(client, gestor, usuario_no_banco, papel):
    usuario = usuario_no_banco(papel=papel)
    for metodo, sufixo, dados in [
        ("get", "", None),
        ("patch", "", {"nome": "Novo Nome"}),
        ("post", "/desativar", None),
    ]:
        assert (
            client.request(
                metodo,
                f"/admin/mentores/{usuario['id']}{sufixo}",
                headers=headers(gestor),
                json=dados,
            ).status_code
            == 404
        )


def test_convite_seguro_e_entrega_pela_fila(client, sql, criar_mentor, processar):
    mentor = criar_mentor()
    token = token_do_email(sql, mentor)
    convite = sql("SELECT * FROM convites_mentor WHERE usuario_id=:u", u=UUID(mentor["id"]))[0]
    assert convite["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(dict(convite))
    assert convite["expira_em"] > convite["criado_em"]
    provedor = ProvedorMemoria()
    processar(provedor)
    assert len(provedor.enviadas) == 1
    assert token in provedor.enviadas[0].texto
    assert SENHA not in provedor.enviadas[0].texto
    email = sql("SELECT * FROM emails_outbox WHERE usuario_id=:u", u=UUID(mentor["id"]))[0]
    assert email["tipo"] == "DEFINICAO_SENHA"
    assert email["status"] == "ENVIADO"
    assert email["corpo_texto"] is None


def test_consulta_convite_exibe_perfil_e_termos(client, sql, criar_mentor, termos_mentor):
    mentor = criar_mentor()
    resposta = client.post(
        "/mentores/convite/consultar",
        json={
            "token": token_do_email(sql, mentor),
            "hackathon_id": termos_mentor["hackathon_id"],
        },
    )
    assert resposta.status_code == 200
    assert resposta.json()["mentor"]["id"] == mentor["id"]
    assert resposta.json()["senha_necessaria"] is True
    assert {t["id"] for t in resposta.json()["termos"]} == set(termos_mentor["termos_ids"])
    assert estado(sql, mentor)["ativo"] is False


def test_ativacao_completa_aceites_login_e_uso_unico(client, sql, criar_mentor, termos_mentor):
    mentor = criar_mentor()
    token = token_do_email(sql, mentor)
    assert (
        client.post("/auth/login", json={"email": mentor["email"], "senha": SENHA}).status_code
        == 401
    )
    resposta = ativar(client, sql, mentor, termos_mentor, nome="Maria Sobrenome")
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["ativo"] is True
    assert resposta.json()["mentor_ativado_em"]
    assert resposta.json()["mentor_perfil_concluido_em"]
    assert estado(sql, mentor)["nome"] == "Maria Sobrenome"
    assert senha_confere(SENHA, estado(sql, mentor)["senha_hash"])
    aceites = sql("SELECT * FROM aceites_termos WHERE usuario_id=:u", u=UUID(mentor["id"]))
    assert {str(a["termo_id"]) for a in aceites} == set(termos_mentor["termos_ids"])
    assert all(a["aceito_em"] for a in aceites)
    assert (
        client.post("/auth/login", json={"email": mentor["email"], "senha": SENHA}).status_code
        == 200
    )
    assert ativar(client, sql, mentor, termos_mentor, token=token).status_code == 400


@pytest.mark.parametrize("tipo", ["expirado", "utilizado", "invalido"])
def test_token_recusado(client, sql, criar_mentor, termos_mentor, tipo):
    mentor = criar_mentor()
    token = token_do_email(sql, mentor)
    if tipo == "expirado":
        sql(
            "UPDATE convites_mentor SET criado_em=now()-interval '2 days',"
            " expira_em=now()-interval '1 day' WHERE usuario_id=:u",
            u=UUID(mentor["id"]),
        )
    elif tipo == "utilizado":
        sql(
            "UPDATE convites_mentor SET utilizado_em=now() WHERE usuario_id=:u",
            u=UUID(mentor["id"]),
        )
    else:
        token = "x" * 43
    assert ativar(client, sql, mentor, termos_mentor, token=token).status_code == 400
    assert estado(sql, mentor)["ativo"] is False


@pytest.mark.parametrize(
    "mudanca",
    [
        {"termos_ids": []},
        {"termos_ids": [str(uuid4()), str(uuid4())]},
        {"nome": " "},
        {"senha": None},
        {"senha": "fraca"},
        {"max_equipes": 10},
    ],
)
def test_ativacao_incompleta_nao_consume_token(client, sql, criar_mentor, termos_mentor, mudanca):
    mentor = criar_mentor()
    assert ativar(client, sql, mentor, termos_mentor, **mudanca).status_code in (409, 422)
    assert estado(sql, mentor)["ativo"] is False
    assert sql("SELECT 1 FROM aceites_termos WHERE usuario_id=:u", u=UUID(mentor["id"])) == []
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200


def test_rejeita_aceite_repetido_ou_desatualizado(client, sql, criar_mentor, termos_mentor):
    mentor = criar_mentor()
    ids = termos_mentor["termos_ids"]
    assert (
        ativar(client, sql, mentor, termos_mentor, termos_ids=[ids[0], ids[0]]).status_code == 422
    )
    sql("UPDATE termos SET vigente=false WHERE id=:t", t=UUID(ids[0]))
    assert ativar(client, sql, mentor, termos_mentor).status_code == 409


def test_reenvio_revoga_token_antigo(client, sql, criar_mentor, gestor, termos_mentor):
    mentor = criar_mentor()
    antigo = token_do_email(sql, mentor)
    assert (
        client.post(f"/admin/mentores/{mentor['id']}/convite", headers=headers(gestor)).status_code
        == 200
    )
    assert token_do_email(sql, mentor) != antigo
    assert ativar(client, sql, mentor, termos_mentor, token=antigo).status_code == 400
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200


def test_desativacao_revoga_acesso_preserva_dados_e_reativacao(
    client, sql, criar_mentor, gestor, termos_mentor
):
    mentor = criar_mentor()
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200
    original = estado(sql, mentor)
    url = f"/admin/mentores/{mentor['id']}"
    resposta = client.post(url + "/desativar", headers=headers(gestor))
    assert resposta.status_code == 200
    assert not resposta.json()["ativo"]
    assert estado(sql, mentor)["senha_hash"] == original["senha_hash"]
    assert estado(sql, mentor)["mentor_ativado_em"] == original["mentor_ativado_em"]
    assert (
        client.get(
            "/auth/me", headers={"Authorization": f"Bearer {criar_token(UUID(mentor['id']))}"}
        ).status_code
        == 401
    )
    assert (
        client.post("/auth/login", json={"email": mentor["email"], "senha": SENHA}).status_code
        == 401
    )
    assert (
        client.post(
            url + "/ativar",
            headers=headers(gestor),
            json={
                "hackathon_id": termos_mentor["hackathon_id"],
            },
        ).status_code
        == 200
    )


def test_admin_nao_ativa_mentor_pendente_e_desativacao_revoga_convite(
    client, sql, criar_mentor, gestor, termos_mentor
):
    mentor = criar_mentor()
    url = f"/admin/mentores/{mentor['id']}"
    assert (
        client.post(
            url + "/ativar",
            headers=headers(gestor),
            json={
                "hackathon_id": termos_mentor["hackathon_id"],
            },
        ).status_code
        == 409
    )
    assert client.post(url + "/desativar", headers=headers(gestor)).status_code == 200
    assert ativar(client, sql, mentor, termos_mentor).status_code == 400


def test_alterar_email_exige_nova_ativacao(
    client, sql, criar_mentor, gestor, termos_mentor, novo_email
):
    mentor = criar_mentor()
    antigo = token_do_email(sql, mentor)
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200
    email = novo_email()
    resposta = client.patch(
        f"/admin/mentores/{mentor['id']}", headers=headers(gestor), json={"email": email}
    )
    assert resposta.status_code == 200
    assert not resposta.json()["ativo"]
    assert estado(sql, mentor)["senha_hash"] is None
    assert ativar(client, sql, mentor, termos_mentor, token=antigo).status_code == 400
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200


def test_ativacoes_simultaneas_consumem_token_uma_vez(client, sql, criar_mentor, termos_mentor):
    mentor = criar_mentor()
    dados = {**PERFIL, **termos_mentor, "senha": SENHA, "token": token_do_email(sql, mentor)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        respostas = list(
            pool.map(lambda _: client.post("/mentores/ativacao", json=dados), range(2))
        )
    assert sorted(r.status_code for r in respostas) == [200, 400]


def elegivel(mentor, hackathon_id):
    async def executar():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with AsyncSession(engine) as db:
                return await validar_elegibilidade(db, UUID(mentor["id"]), UUID(hackathon_id))
        finally:
            await engine.dispose()

    return asyncio.run(executar())


def test_elegibilidade_be_s5_11(client, sql, criar_mentor, gestor, termos_mentor):
    mentor = criar_mentor()
    h = termos_mentor["hackathon_id"]
    with pytest.raises(HTTPException) as erro:
        elegivel(mentor, h)
    assert erro.value.status_code == 409
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200
    assert elegivel(mentor, h).max_equipes == 2
    sql("DELETE FROM aceites_termos WHERE usuario_id=:u", u=UUID(mentor["id"]))
    with pytest.raises(HTTPException):
        elegivel(mentor, h)
    assert (
        client.post(
            f"/admin/mentores/{mentor['id']}/desativar", headers=headers(gestor)
        ).status_code
        == 200
    )
    with pytest.raises(HTTPException):
        elegivel(mentor, h)


def test_falha_de_fila_mantem_cadastro_pendente(client, sql, criar_mentor, monkeypatch):
    async def falha(*args, **kwargs):
        return False

    monkeypatch.setattr("app.services.mentor.enfileirar", falha)
    mentor = criar_mentor()
    assert not estado(sql, mentor)["ativo"]
    assert sql("SELECT 1 FROM emails_outbox WHERE usuario_id=:u", u=UUID(mentor["id"])) == []


def test_rollback_nao_deixa_cadastro_convite_ou_email(client, sql, gestor, novo_email, monkeypatch):
    from app.services.mentor import convidar

    async def falhar_depois_de_enfileirar(db, mentor):
        await convidar(db, mentor)
        raise HTTPException(409, "Falha simulada")

    monkeypatch.setattr("app.services.mentor.convidar", falhar_depois_de_enfileirar)
    email = novo_email()
    assert (
        client.post(
            "/admin/mentores",
            headers=headers(gestor),
            json={
                **PERFIL,
                "email": email,
                "max_equipes": 2,
            },
        ).status_code
        == 409
    )
    assert sql("SELECT 1 FROM usuarios WHERE email=:e", e=email) == []
    assert sql("SELECT 1 FROM emails_outbox WHERE destinatario_email=:e", e=email) == []


@pytest.mark.parametrize("papel", ["COMITE_CIENTIFICO", "ORGANIZADOR", "DEV"])
def test_operacoes_administrativas_autorizadas(
    client, sql, criar_mentor, usuario_no_banco, termos_mentor, papel
):
    mentor = criar_mentor()
    cabecalho = headers(usuario_no_banco(papel=papel))
    url = f"/admin/mentores/{mentor['id']}"
    assert client.get("/admin/mentores", headers=cabecalho).status_code == 200
    assert client.get(url, headers=cabecalho).status_code == 200
    assert client.patch(url, headers=cabecalho, json={"max_equipes": 3}).status_code == 200
    assert client.post(url + "/convite", headers=cabecalho).status_code == 200
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200
    assert client.post(url + "/desativar", headers=cabecalho).status_code == 200
    assert (
        client.post(
            url + "/ativar",
            headers=cabecalho,
            json={
                "hackathon_id": termos_mentor["hackathon_id"],
            },
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "mudanca",
    [
        {"senha": SENHA},
        {"max_equipes": True},
        {"max_equipes": 1.5},
        {"area_atuacao": None},
        {"empresa_parceira": ""},
        {"max_equipes": None},
    ],
)
def test_cadastro_generico_nao_contorna_rn33(client, gestor, novo_email, mudanca):
    assert (
        client.post(
            "/admin/usuarios",
            headers=headers(gestor),
            json={
                **PERFIL,
                "papel": "MENTOR",
                "email": novo_email(),
                "max_equipes": 2,
                **mudanca,
            },
        ).status_code
        == 422
    )


def test_cadastro_generico_envia_convite_sem_senha(client, sql, gestor, novo_email):
    resposta = client.post(
        "/admin/usuarios",
        headers=headers(gestor),
        json={
            **PERFIL,
            "papel": "MENTOR",
            "email": novo_email(),
            "max_equipes": 2,
        },
    )
    assert resposta.status_code == 201
    mentor = resposta.json()
    assert not mentor["ativo"]
    assert estado(sql, mentor)["senha_hash"] is None
    assert token_do_email(sql, mentor)


def test_cadastro_dos_demais_perfis_preserva_contrato(client, gestor, novo_email):
    # A validação estrita da capacidade é específica do perfil MENTOR.
    dados = {"papel": "COMITE_TECNICO", "email": novo_email(), "senha": SENHA, "max_equipes": "2"}
    resposta = client.post("/admin/usuarios", headers=headers(gestor), json=dados)
    assert resposta.status_code == 201
    assert resposta.json()["ativo"] is True
    assert resposta.json()["max_equipes"] == 2
    del dados["senha"]
    dados["email"] = novo_email()
    assert client.post("/admin/usuarios", headers=headers(gestor), json=dados).status_code == 422


def test_convite_nao_autentica_nem_acessa_rota_de_negocio(client, sql, criar_mentor, termos_mentor):
    mentor = criar_mentor()
    token = token_do_email(sql, mentor)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    cabecalho = {"Authorization": f"Bearer {criar_token(UUID(mentor['id']))}"}
    url = f"/hackathons/{termos_mentor['hackathon_id']}/termos/vigentes"
    assert client.get(url, headers=cabecalho).status_code == 401


def test_aceites_de_outra_edicao_nao_ativam(client, sql, criar_mentor, termos_mentor):
    mentor = criar_mentor()
    assert ativar(client, sql, mentor, termos_mentor, hackathon_id=str(uuid4())).status_code == 404
    assert not estado(sql, mentor)["ativo"]


def test_falha_apos_aceites_desfaz_ativacao(client, sql, criar_mentor, termos_mentor, monkeypatch):
    from app.controllers.termo import registrar_aceites

    async def falhar(db, usuario_id, termos_ids):
        await registrar_aceites(db, usuario_id, termos_ids)
        raise HTTPException(409, "Falha simulada após aceite")

    mentor = criar_mentor()
    with monkeypatch.context() as contexto:
        contexto.setattr("app.services.mentor.registrar_aceites", falhar)
        assert ativar(client, sql, mentor, termos_mentor).status_code == 409
    assert not estado(sql, mentor)["ativo"]
    assert estado(sql, mentor)["senha_hash"] is None
    assert sql("SELECT 1 FROM aceites_termos WHERE usuario_id=:u", u=UUID(mentor["id"])) == []
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200


def test_reativacao_exige_termos_e_convite_renovado_preserva_senha(
    client, sql, criar_mentor, gestor, termos_mentor
):
    mentor = criar_mentor()
    assert ativar(client, sql, mentor, termos_mentor).status_code == 200
    senha_original = estado(sql, mentor)["senha_hash"]
    url = f"/admin/mentores/{mentor['id']}"
    assert client.post(url + "/desativar", headers=headers(gestor)).status_code == 200
    sql("DELETE FROM aceites_termos WHERE usuario_id=:u", u=UUID(mentor["id"]))
    assert (
        client.post(
            url + "/ativar",
            headers=headers(gestor),
            json={
                "hackathon_id": termos_mentor["hackathon_id"],
            },
        ).status_code
        == 409
    )
    assert client.post(url + "/convite", headers=headers(gestor)).status_code == 200
    assert ativar(client, sql, mentor, termos_mentor, senha=None).status_code == 200
    assert estado(sql, mentor)["senha_hash"] == senha_original

    assert client.post(url + "/desativar", headers=headers(gestor)).status_code == 200
    assert client.post(url + "/convite", headers=headers(gestor)).status_code == 200
    consulta = client.post(
        "/mentores/convite/consultar",
        json={
            "token": token_do_email(sql, mentor),
            "hackathon_id": termos_mentor["hackathon_id"],
        },
    )
    assert consulta.json()["senha_necessaria"] is False
    assert ativar(client, sql, mentor, termos_mentor, senha="OutraSenha456").status_code == 200
    assert senha_confere("OutraSenha456", estado(sql, mentor)["senha_hash"])


def test_desativacao_simultanea_a_ativacao_impede_acesso(
    client, sql, criar_mentor, gestor, termos_mentor
):
    mentor = criar_mentor()
    dados = {**PERFIL, **termos_mentor, "senha": SENHA, "token": token_do_email(sql, mentor)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        ativacao = pool.submit(client.post, "/mentores/ativacao", json=dados)
        desativacao = pool.submit(
            client.post, f"/admin/mentores/{mentor['id']}/desativar", headers=headers(gestor)
        )
        assert desativacao.result().status_code == 200
        assert ativacao.result().status_code in (200, 400)
    assert not estado(sql, mentor)["ativo"]
