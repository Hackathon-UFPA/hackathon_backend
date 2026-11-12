"""BE-S5-05: rotas administrativas da fila de e-mails (RNF28): permissões, filtros e reenvio."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from app.const.enums import StatusEmail, TipoEmail
from app.integrations.email import ProvedorMemoria
from app.schemas.email import EmailResponse
from tests.helpers_email import inserir_email, linha_do_email
from tests.test_convites import com_token

CAMPOS_DA_RESPOSTA = set(EmailResponse.model_fields)


@pytest.fixture(autouse=True)
def _fila_limpa(fila_vazia):
    yield


@pytest.fixture
def organizador(usuario_no_banco):
    return usuario_no_banco(papel="ORGANIZADOR", senha=None)


def autenticado(usuario) -> dict:
    return com_token(usuario["id"])


# --- Quem acessa ---


def rotas():
    inexistente = uuid4()
    return [
        ("get", "/admin/emails"),
        ("get", f"/admin/emails/{inexistente}"),
        ("post", f"/admin/emails/{inexistente}/reenviar"),
    ]


@pytest.mark.parametrize(("metodo", "caminho"), rotas(), ids=["listar", "consultar", "reenviar"])
def test_sem_token_responde_401(client, metodo, caminho):
    assert getattr(client, metodo)(caminho).status_code == 401


@pytest.mark.parametrize(("metodo", "caminho"), rotas(), ids=["listar", "consultar", "reenviar"])
@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO", "COMITE_CIENTIFICO"])
def test_perfis_sem_permissao_respondem_403(client, usuario_no_banco, metodo, caminho, papel):
    usuario = usuario_no_banco(papel=papel, senha=None)

    resposta = getattr(client, metodo)(caminho, headers=autenticado(usuario))

    assert resposta.status_code == 403


@pytest.mark.parametrize(("metodo", "caminho"), rotas(), ids=["listar", "consultar", "reenviar"])
def test_organizador_com_conta_pendente_responde_403(client, usuario_no_banco, metodo, caminho):
    usuario = usuario_no_banco(papel="ORGANIZADOR", senha=None, situacao_conta="PENDENTE")

    assert getattr(client, metodo)(caminho, headers=autenticado(usuario)).status_code == 403


@pytest.mark.parametrize("papel", ["ORGANIZADOR", "DEV"])
def test_organizador_e_dev_acessam(client, usuario_no_banco, papel):
    usuario = usuario_no_banco(papel=papel, senha=None)

    assert client.get("/admin/emails", headers=autenticado(usuario)).status_code == 200
    inexistente = f"/admin/emails/{uuid4()}"
    assert client.get(inexistente, headers=autenticado(usuario)).status_code == 404
    assert client.post(f"{inexistente}/reenviar", headers=autenticado(usuario)).status_code == 404


# --- Listagem ---


def test_lista_os_mais_recentes_primeiro(client, sql, organizador):
    antigo = inserir_email(sql, "a@testes.com", criado_em_segundos=-300)
    recente = inserir_email(sql, "b@testes.com", criado_em_segundos=-10)
    meio = inserir_email(sql, "c@testes.com", criado_em_segundos=-100)

    resposta = client.get("/admin/emails", headers=autenticado(organizador))

    assert resposta.status_code == 200
    assert [e["id"] for e in resposta.json()] == [str(recente), str(meio), str(antigo)]


def test_lista_vazia_devolve_lista_vazia(client, organizador):
    resposta = client.get("/admin/emails", headers=autenticado(organizador))

    assert resposta.status_code == 200 and resposta.json() == []


def test_resposta_nunca_traz_o_conteudo_da_mensagem_nem_a_chave(client, sql, organizador):
    email_id = inserir_email(sql, "a@testes.com", chave="convite:segredo")

    [item] = client.get("/admin/emails", headers=autenticado(organizador)).json()
    detalhe = client.get(f"/admin/emails/{email_id}", headers=autenticado(organizador)).json()

    for resposta in (item, detalhe):
        assert set(resposta) == CAMPOS_DA_RESPOSTA
        assert "corpo_texto" not in resposta and "corpo_html" not in resposta
        assert "chave_idempotencia" not in resposta
        assert "Texto do e-mail" not in str(resposta)


def test_filtra_por_status(client, sql, organizador):
    pendente = inserir_email(sql, "a@testes.com")
    falha = inserir_email(sql, "b@testes.com", status="FALHA", tentativas=5)
    inserir_email(sql, "c@testes.com", status="ENVIADO", com_corpo=False, tentativas=1)

    resposta = client.get("/admin/emails?status=FALHA", headers=autenticado(organizador))

    assert [e["id"] for e in resposta.json()] == [str(falha)]
    assert str(pendente) not in str(resposta.json())


def test_filtra_por_tipo(client, sql, organizador):
    inserir_email(sql, "a@testes.com", tipo="CONVITE_EQUIPE")
    protocolo = inserir_email(sql, "b@testes.com", tipo="PROTOCOLO_PROPOSTA")

    resposta = client.get("/admin/emails?tipo=PROTOCOLO_PROPOSTA", headers=autenticado(organizador))

    assert [e["id"] for e in resposta.json()] == [str(protocolo)]


def test_filtra_por_destinatario_sem_diferenciar_maiusculas(client, sql, organizador):
    procurado = inserir_email(sql, "Maria.Souza@Testes.com")
    inserir_email(sql, "outra@testes.com")

    resposta = client.get(
        "/admin/emails?destinatario=maria.souza@testes.COM", headers=autenticado(organizador)
    )

    assert [e["id"] for e in resposta.json()] == [str(procurado)]


def test_filtros_combinados(client, sql, organizador):
    alvo = inserir_email(sql, "a@testes.com", tipo="CONVITE_EQUIPE", status="FALHA", tentativas=5)
    inserir_email(sql, "a@testes.com", tipo="CONVITE_EQUIPE")  # mesmo destinatário, outro status
    inserir_email(sql, "a@testes.com", tipo="PROTOCOLO_PROPOSTA", status="FALHA", tentativas=5)

    resposta = client.get(
        "/admin/emails?status=FALHA&tipo=CONVITE_EQUIPE&destinatario=a@testes.com",
        headers=autenticado(organizador),
    )

    assert [e["id"] for e in resposta.json()] == [str(alvo)]


def test_paginacao_por_limite_e_deslocamento(client, sql, organizador):
    ids = [inserir_email(sql, "a@testes.com", criado_em_segundos=-n) for n in (50, 40, 30, 20, 10)]
    mais_novos_primeiro = [str(i) for i in reversed(ids)]

    primeira = client.get("/admin/emails?limite=2", headers=autenticado(organizador)).json()
    segunda = client.get(
        "/admin/emails?limite=2&deslocamento=2", headers=autenticado(organizador)
    ).json()
    ultima = client.get(
        "/admin/emails?limite=2&deslocamento=4", headers=autenticado(organizador)
    ).json()

    assert [e["id"] for e in primeira] == mais_novos_primeiro[:2]
    assert [e["id"] for e in segunda] == mais_novos_primeiro[2:4]
    assert [e["id"] for e in ultima] == mais_novos_primeiro[4:]


@pytest.mark.parametrize(
    "consulta",
    ["limite=0", "limite=101", "limite=abc", "deslocamento=-1", "status=INEXISTENTE", "tipo=OUTRO"],
)
def test_parametros_invalidos_respondem_422(client, organizador, consulta):
    resposta = client.get(f"/admin/emails?{consulta}", headers=autenticado(organizador))

    assert resposta.status_code == 422
    assert isinstance(resposta.json()["detail"], list)


def test_aceita_o_limite_maximo_de_100(client, organizador):
    assert (
        client.get("/admin/emails?limite=100", headers=autenticado(organizador)).status_code == 200
    )


# --- Consulta de um e-mail ---


def test_consulta_mostra_a_situacao_do_envio(client, sql, organizador):
    email_id = inserir_email(sql, "a@testes.com", status="FALHA", tentativas=5)
    sql("UPDATE emails_outbox SET ultimo_erro = 'ErroX 550' WHERE id = :id", id=email_id)

    resposta = client.get(f"/admin/emails/{email_id}", headers=autenticado(organizador))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["id"] == str(email_id)
    assert corpo["status"] == "FALHA"
    assert corpo["tentativas"] == 5 and corpo["max_tentativas"] == 5
    assert corpo["ultimo_erro"] == "ErroX 550"
    assert corpo["destinatario_email"] == "a@testes.com"
    assert corpo["enviado_em"] is None


def test_consulta_de_id_inexistente_responde_404(client, organizador):
    resposta = client.get(f"/admin/emails/{uuid4()}", headers=autenticado(organizador))

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "E-mail não encontrado."}


@pytest.mark.parametrize("metodo", ["get", "post"])
def test_id_que_nao_e_uuid_responde_422(client, organizador, metodo):
    caminho = "/admin/emails/nao-e-uuid" + ("/reenviar" if metodo == "post" else "")

    resposta = getattr(client, metodo)(caminho, headers=autenticado(organizador))

    assert resposta.status_code == 422


# --- Reenvio ---


def test_reenviar_devolve_o_email_que_falhou_para_a_fila(client, sql, organizador):
    email_id = inserir_email(sql, "a@testes.com", status="FALHA", tentativas=5)
    sql("UPDATE emails_outbox SET ultimo_erro = 'ErroX 550' WHERE id = :id", id=email_id)

    resposta = client.post(f"/admin/emails/{email_id}/reenviar", headers=autenticado(organizador))

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["status"] == "PENDENTE" and corpo["tentativas"] == 0
    assert corpo["ultimo_erro"] == "ErroX 550"  # o histórico do motivo anterior fica
    linha = linha_do_email(sql, email_id)
    assert linha["status"] == "PENDENTE" and linha["tentativas"] == 0
    assert linha["segundos_ate_a_proxima"] <= 0
    assert linha["corpo_texto"] is not None


def test_o_worker_envia_o_email_reenviado(client, sql, organizador, processar):
    email_id = inserir_email(sql, "a@testes.com", status="FALHA", tentativas=5)
    client.post(f"/admin/emails/{email_id}/reenviar", headers=autenticado(organizador))
    provedor = ProvedorMemoria()

    resumo = processar(provedor)

    assert resumo.enviados == 1 and len(provedor.enviadas) == 1
    consulta = client.get(f"/admin/emails/{email_id}", headers=autenticado(organizador)).json()
    assert consulta["status"] == "ENVIADO" and consulta["tentativas"] == 1
    assert consulta["enviado_em"] is not None


@pytest.mark.parametrize(
    ("status", "trecho"),
    [
        ("PENDENTE", "ainda está na fila"),
        ("ENVIANDO", "ainda está na fila"),
        ("ENVIADO", "já foi enviado"),
    ],
)
def test_so_reenvia_o_que_falhou(client, sql, organizador, status, trecho):
    reserva = 300 if status == "ENVIANDO" else None
    email_id = inserir_email(
        sql,
        "a@testes.com",
        status=status,
        tentativas=1,
        com_corpo=status != "ENVIADO",
        reservado_ate_em_segundos=reserva,
    )
    antes = linha_do_email(sql, email_id)

    resposta = client.post(f"/admin/emails/{email_id}/reenviar", headers=autenticado(organizador))

    assert resposta.status_code == 409
    assert trecho in resposta.json()["detail"]
    depois = linha_do_email(sql, email_id)
    assert (depois["status"], depois["tentativas"]) == (antes["status"], antes["tentativas"])


def test_reenviar_duas_vezes_seguidas_na_segunda_responde_409(client, sql, organizador):
    email_id = inserir_email(sql, "a@testes.com", status="FALHA", tentativas=5)
    url = f"/admin/emails/{email_id}/reenviar"

    assert client.post(url, headers=autenticado(organizador)).status_code == 200
    assert client.post(url, headers=autenticado(organizador)).status_code == 409


def test_dois_reenvios_simultaneos_resultam_em_um_sucesso_e_um_conflito(client, sql, organizador):
    email_id = inserir_email(sql, "a@testes.com", status="FALHA", tentativas=5)
    barreira = Barrier(2)

    def reenviar():
        barreira.wait()
        return client.post(
            f"/admin/emails/{email_id}/reenviar", headers=autenticado(organizador)
        ).status_code

    with ThreadPoolExecutor(2) as pool:
        codigos = sorted(f.result() for f in [pool.submit(reenviar), pool.submit(reenviar)])

    assert codigos == [200, 409]
    assert linha_do_email(sql, email_id)["status"] == "PENDENTE"


# --- Swagger ---


def test_swagger_documenta_as_rotas_de_email(client):
    documento = client.get("/openapi.json").json()
    caminhos = documento["paths"]

    listar = caminhos["/admin/emails"]["get"]
    consultar = caminhos["/admin/emails/{email_id}"]["get"]
    reenviar = caminhos["/admin/emails/{email_id}/reenviar"]["post"]
    for rota in (listar, consultar, reenviar):
        assert rota["tags"] == ["E-mails"]
        assert rota["summary"] and rota["description"]
    assert "nunca o conteúdo" in listar["description"]
    assert "Não traz o conteúdo" in consultar["description"]
    assert "duplicaria" in reenviar["description"]
    assert set(listar["responses"]) == {"200", "401", "403", "422"}
    assert set(consultar["responses"]) == {"200", "401", "403", "404", "422"}
    assert set(reenviar["responses"]) == {"200", "401", "403", "404", "409", "422"}
    for rota, codigo in ((reenviar, "409"), (consultar, "404"), (listar, "403")):
        erro = rota["responses"][codigo]["content"]["application/json"]["schema"]
        assert erro == {"$ref": "#/components/schemas/ErroResponse"}

    parametros = {p["name"]: p["schema"] for p in listar["parameters"]}
    assert set(parametros) == {"status", "tipo", "destinatario", "limite", "deslocamento"}
    assert parametros["limite"]["default"] == 50
    assert parametros["limite"]["minimum"] == 1 and parametros["limite"]["maximum"] == 100
    assert parametros["deslocamento"]["minimum"] == 0
    componentes = documento["components"]["schemas"]
    assert componentes["StatusEmail"]["enum"] == [s.value for s in StatusEmail]
    assert componentes["TipoEmail"]["enum"] == [t.value for t in TipoEmail]


def test_swagger_nao_expoe_o_conteudo_da_mensagem_no_schema(client):
    esquema = client.get("/openapi.json").json()["components"]["schemas"]["EmailResponse"]

    assert set(esquema["properties"]) == CAMPOS_DA_RESPOSTA
    assert "corpo_texto" not in esquema["properties"]
    assert "chave_idempotencia" not in esquema["properties"]
    assert esquema["examples"]
