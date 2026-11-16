"""BE-S5-04: central de notificações in-app (RF19, RF22, RF28, RF33, RF38, RF53, RF60, RF61).

Cobre o serviço `notificar` (idempotência, concorrência, falha isolada, CHAT sem e-mail), a API de
leitura (privacidade, lidas e não lidas, paginação), a compatibilidade do RF33 e a integração
com os fluxos que passaram a notificar.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

from app.const.config import settings
from app.const.enums import TipoNotificacao
from app.services.notificacao import notificar
from tests import test_atribuicoes_mentor, test_email_eventos
from tests.test_atribuicoes_mentor import atribuir, substituir
from tests.test_convites import com_token
from tests.test_email_fila import com_sessao

# Cenários dos outros testes, reaproveitados como fixtures deste arquivo
inscricao = test_email_eventos.inscricao
envio = test_email_eventos.envio
resultado = test_email_eventos.resultado
cenario_mentoria = test_atribuicoes_mentor.s

ROTA = "/me/notificacoes"


@pytest.fixture(autouse=True)
def _fila_limpa(fila_vazia):
    yield


def criar(usuarios, tipo=TipoNotificacao.CONVITE, chave=None, **extras):
    """Cria avisos pela função única, em uma transação confirmada. Devolve o retorno dela."""
    chave = chave or f"teste:{uuid4()}"

    async def acao(db):
        criadas = await notificar(
            db,
            [u["id"] for u in usuarios],
            tipo,
            extras.pop("titulo", "Título"),
            extras.pop("mensagem", "Mensagem"),
            chave=chave,
            **extras,
        )
        await db.commit()
        return criadas

    return com_sessao(acao)


def linhas(sql, usuario, **filtros):
    return sql(
        "SELECT * FROM notificacoes WHERE usuario_id = :u ORDER BY criado_em, id", u=usuario["id"]
    )


def listar(client, usuario, **params):
    return client.get(ROTA, headers=com_token(usuario["id"]), params=params)


def nao_lidas(client, usuario) -> int:
    resposta = client.get(f"{ROTA}/nao-lidas/contagem", headers=com_token(usuario["id"]))
    assert resposta.status_code == 200
    return resposta.json()["nao_lidas"]


@pytest.fixture
def pessoas(usuario_no_banco):
    return [usuario_no_banco(senha=None) for _ in range(3)]


# --- Serviço único: idempotência, concorrência e falha isolada ---


def test_notificar_grava_um_aviso_por_destinatario(sql, pessoas):
    referencia = uuid4()
    chave = "teste:basico"

    assert (
        criar(
            pessoas[:2],
            TipoNotificacao.PROPOSTA,
            chave,
            referencia_tipo="CONVITE",
            referencia_id=referencia,
            dados={"id": referencia, "resposta": "ACEITO"},
        )
        == 2
    )

    [aviso] = linhas(sql, pessoas[0])
    assert aviso["tipo"] == "PROPOSTA"
    assert (aviso["titulo"], aviso["mensagem"]) == ("Título", "Mensagem")
    assert aviso["referencia_tipo"] == "CONVITE" and aviso["referencia_id"] == referencia
    assert aviso["dados"] == {"id": str(referencia), "resposta": "ACEITO"}
    assert aviso["lida_em"] is None and aviso["chave_idempotencia"] == chave
    assert len(linhas(sql, pessoas[1])) == 1 and linhas(sql, pessoas[2]) == []


def test_repetir_o_mesmo_fato_nao_duplica(sql, pessoas):
    assert criar(pessoas[:2], chave="teste:fato") == 2
    assert criar(pessoas[:2], chave="teste:fato") == 0
    # Quem ainda não tinha o aviso do fato recebe; os demais não repetem
    assert criar(pessoas, chave="teste:fato") == 1
    assert [len(linhas(sql, p)) for p in pessoas] == [1, 1, 1]
    # Outro fato é outro aviso
    assert criar(pessoas[:1], chave="teste:outro") == 1
    assert len(linhas(sql, pessoas[0])) == 2


def test_destinatario_repetido_na_lista_recebe_uma_vez(sql, pessoas):
    assert criar([pessoas[0], pessoas[0], pessoas[1]]) == 2
    assert len(linhas(sql, pessoas[0])) == 1


def test_sem_destinatarios_nao_faz_nada(sql):
    assert criar([]) == 0


def test_a_mesma_chave_vale_por_usuario(sql, pessoas):
    criar(pessoas[:1], chave="teste:igual")
    criar(pessoas[1:2], chave="teste:igual")
    assert len(linhas(sql, pessoas[0])) == len(linhas(sql, pessoas[1])) == 1


def test_gravacoes_simultaneas_do_mesmo_fato_criam_um_so_aviso(sql, pessoas):
    paralelos = 8
    barreira = Barrier(paralelos)

    def executar(_):
        async def acao(db):
            barreira.wait(timeout=10)
            criadas = await notificar(
                db,
                [p["id"] for p in pessoas],
                TipoNotificacao.CONVITE,
                "T",
                "M",
                chave="teste:corrida",
            )
            await db.commit()
            return criadas

        return com_sessao(acao)

    with ThreadPoolExecutor(paralelos) as pool:
        criadas = list(pool.map(executar, range(paralelos)))

    assert sum(criadas) == 3
    assert [len(linhas(sql, p)) for p in pessoas] == [1, 1, 1]


def test_resultado_nao_passa_pela_funcao_unica(pessoas):
    with pytest.raises(ValueError, match="RF33"):
        criar(pessoas[:1], TipoNotificacao.RESULTADO)


def test_referencia_exige_tipo_e_id_juntos(pessoas):
    with pytest.raises(ValueError, match="referência"):
        criar(pessoas[:1], referencia_tipo="CONVITE")


def test_falha_ao_gravar_nao_derruba_a_acao_principal(sql, pessoas):
    """Destinatário inexistente quebra a gravação do aviso. A ação principal (aqui, o nome do
    usuário) continua válida na mesma transação, e o retorno None avisa que falhou."""

    async def acao(db):
        await db.exec(
            __import__("sqlalchemy").text(
                "UPDATE usuarios SET nome = 'Ação principal' WHERE id = :u"
            ),
            params={"u": pessoas[0]["id"]},
        )
        resultado_aviso = await notificar(
            db, [uuid4()], TipoNotificacao.CONVITE, "T", "M", chave="teste:falha"
        )
        await db.commit()
        return resultado_aviso

    assert com_sessao(acao) is None
    assert sql("SELECT nome FROM usuarios WHERE id = :u", u=pessoas[0]["id"])[0]["nome"] == (
        "Ação principal"
    )
    assert sql("SELECT 1 FROM notificacoes WHERE chave_idempotencia = 'teste:falha'") == []


def test_erro_da_escrita_anterior_nao_e_engolido_como_falha_do_aviso(sql, pessoas):
    """O flush acontece fora do try: uma violação da escrita do fato gerador chega a quem chamou."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Notificacao

    async def acao(db):
        db.add(
            Notificacao(
                usuario_id=pessoas[0]["id"],
                tipo=TipoNotificacao.CONVITE,
                titulo="T",
                mensagem="M",
                chave_idempotencia="",  # viola ck_notificacoes_chave
            )
        )
        await notificar(db, [pessoas[0]["id"]], TipoNotificacao.CONVITE, "T", "M", chave="teste:x")

    with pytest.raises(IntegrityError):
        com_sessao(acao)


# --- CHAT: só notificação interna, nunca e-mail (decisão de 05/11, RN32) ---


def test_chat_nao_enfileira_email(sql, pessoas, monkeypatch):
    async def proibido(*_, **__):
        raise AssertionError("O chat não pode usar o e-mail")

    monkeypatch.setattr("app.services.email.enfileirar", proibido)
    monkeypatch.setattr("app.services.email_eventos.enfileirar", proibido)

    assert criar(pessoas, TipoNotificacao.CHAT, "chat:conversa:1") == 3

    assert [len(linhas(sql, p)) for p in pessoas] == [1, 1, 1]
    assert sql("SELECT 1 FROM notificacoes WHERE tipo = 'CHAT'")
    assert sql("SELECT 1 FROM emails_outbox") == []


def test_o_servico_de_notificacao_nao_depende_do_modulo_de_email():
    codigo = Path("app/services/notificacao.py").read_text(encoding="utf-8")
    assert not re.search(
        r"^\s*(from|import)\s+app\.(services\.email|jobs|integrations)", codigo, re.M
    )


def test_todos_os_tipos_sao_aceitos(sql, pessoas):
    for tipo in TipoNotificacao:
        if tipo != TipoNotificacao.RESULTADO:
            assert criar(pessoas[:1], tipo, f"teste:tipo:{tipo}") == 1


# --- API de leitura: listagem, contagem, leitura e paginação ---


def test_listagem_exige_login(client):
    assert client.get(ROTA).status_code == 401
    assert client.get(f"{ROTA}/nao-lidas/contagem").status_code == 401
    assert client.post(f"{ROTA}/lidas").status_code == 401
    assert client.post(f"{ROTA}/{uuid4()}/lida").status_code == 401


def test_conta_pendente_nao_acessa(client, usuario_no_banco):
    pendente = usuario_no_banco(senha=None, situacao_conta="PENDENTE")
    assert listar(client, pendente).status_code == 403


def test_item_generico_tem_os_campos_da_central(client, pessoas):
    referencia = uuid4()
    criar(
        pessoas[:1],
        TipoNotificacao.ACEITE,
        referencia_tipo="CONVITE",
        referencia_id=referencia,
        dados={"resposta": "RECUSADO"},
    )

    [item] = listar(client, pessoas[0]).json()

    assert item["id"] == item["notificacao_id"]
    assert item["tipo"] == "ACEITE" and item["titulo"] == "Título"
    assert item["mensagem"] == "Mensagem" and item["dados"] == {"resposta": "RECUSADO"}
    assert item["referencia"] == {"tipo": "CONVITE", "id": str(referencia)}
    assert item["lida_em"] is None and item["criado_em"]


def test_marcar_como_lida_e_idempotente(client, pessoas):
    criar(pessoas[:1], chave="teste:a")
    criar(pessoas[:1], chave="teste:b")
    primeiro, outro = listar(client, pessoas[0]).json()
    assert nao_lidas(client, pessoas[0]) == 2

    marcada = client.post(
        f"{ROTA}/{primeiro['notificacao_id']}/lida", headers=com_token(pessoas[0]["id"])
    )
    assert marcada.status_code == 200 and marcada.json()["lida_em"]
    de_novo = client.post(
        f"{ROTA}/{primeiro['notificacao_id']}/lida", headers=com_token(pessoas[0]["id"])
    )

    assert de_novo.status_code == 200
    assert de_novo.json()["lida_em"] == marcada.json()["lida_em"]  # não é sobrescrito
    assert nao_lidas(client, pessoas[0]) == 1
    restante = listar(client, pessoas[0], lida="false").json()
    assert [i["notificacao_id"] for i in restante] == [outro["notificacao_id"]]
    lidas = listar(client, pessoas[0], lida="true").json()
    assert [i["notificacao_id"] for i in lidas] == [primeiro["notificacao_id"]]


def test_marcar_todas_como_lidas(client, pessoas):
    for n in range(3):
        criar(pessoas[:2], chave=f"teste:{n}")

    assert client.post(f"{ROTA}/lidas", headers=com_token(pessoas[0]["id"])).json() == {
        "marcadas": 3
    }
    assert client.post(f"{ROTA}/lidas", headers=com_token(pessoas[0]["id"])).json() == {
        "marcadas": 0
    }
    assert nao_lidas(client, pessoas[0]) == 0
    assert nao_lidas(client, pessoas[1]) == 3  # as dos outros ficam como estavam
    assert len(listar(client, pessoas[0], lida="true").json()) == 3


def test_filtro_por_tipo(client, pessoas):
    criar(pessoas[:1], TipoNotificacao.CONVITE, "teste:1")
    criar(pessoas[:1], TipoNotificacao.CHAT, "teste:2")

    [chat] = listar(client, pessoas[0], tipo="CHAT").json()

    assert chat["tipo"] == "CHAT"
    assert listar(client, pessoas[0], tipo="INVALIDO").status_code == 422


def test_paginacao_com_total_no_cabecalho(client, pessoas):
    for n in range(5):
        criar(pessoas[:1], chave=f"teste:{n:02d}", mensagem=f"M{n}")
    criar(pessoas[1:2], chave="teste:de-outro")

    todas = listar(client, pessoas[0])
    pagina1 = listar(client, pessoas[0], limite=2, deslocamento=0)
    pagina2 = listar(client, pessoas[0], limite=2, deslocamento=2)
    pagina3 = listar(client, pessoas[0], limite=2, deslocamento=4)

    assert todas.headers["X-Total-Count"] == "5"
    for pagina in (pagina1, pagina2, pagina3):
        assert pagina.headers["X-Total-Count"] == "5"
    ids = [i["notificacao_id"] for p in (pagina1, pagina2, pagina3) for i in p.json()]
    assert ids == [i["notificacao_id"] for i in todas.json()]
    assert [len(p.json()) for p in (pagina1, pagina2, pagina3)] == [2, 2, 1]
    assert listar(client, pessoas[0], limite=2, deslocamento=9).json() == []
    # Mais recentes primeiro
    assert [i["mensagem"] for i in todas.json()] == ["M4", "M3", "M2", "M1", "M0"]


def test_total_acompanha_o_filtro(client, pessoas):
    criar(pessoas[:1], chave="teste:1")
    criar(pessoas[:1], chave="teste:2")
    primeiro = listar(client, pessoas[0]).json()[0]
    client.post(f"{ROTA}/{primeiro['notificacao_id']}/lida", headers=com_token(pessoas[0]["id"]))

    assert listar(client, pessoas[0], lida="false").headers["X-Total-Count"] == "1"
    assert listar(client, pessoas[0], lida="true").headers["X-Total-Count"] == "1"


@pytest.mark.parametrize(
    "parametros", [{"limite": 0}, {"limite": 101}, {"deslocamento": -1}, {"lida": "talvez"}]
)
def test_parametros_invalidos(client, pessoas, parametros):
    assert listar(client, pessoas[0], **parametros).status_code == 422


def test_o_limite_padrao_e_100(client, pessoas, sql):
    sql(
        "INSERT INTO notificacoes (usuario_id, tipo, titulo, mensagem, chave_idempotencia)"
        " SELECT :u, 'CHAT', 't', 'm', 'massa:' || g FROM generate_series(1, 105) g",
        u=pessoas[0]["id"],
    )

    resposta = listar(client, pessoas[0])

    assert len(resposta.json()) == 100
    assert resposta.headers["X-Total-Count"] == "105"


def test_cors_expoe_o_total_ao_navegador(client, pessoas):
    origem = settings.cors_origins[0]
    resposta = client.get(ROTA, headers={**com_token(pessoas[0]["id"]), "Origin": origem})
    expostos = {
        h.strip().lower() for h in resposta.headers["access-control-expose-headers"].split(",")
    }
    assert {"x-total-count", "retry-after"} <= expostos


# --- Privacidade: cada um vê e marca só as próprias (404, não 403) ---


def test_ninguem_ve_notificacao_de_outro(client, pessoas, usuario_no_banco):
    criar(pessoas[:1], mensagem="Só da primeira")
    organizador = usuario_no_banco(papel="ORGANIZADOR", senha=None)
    dev = usuario_no_banco(papel="DEV", senha=None)

    assert len(listar(client, pessoas[0]).json()) == 1
    for outro in (pessoas[1], organizador, dev):
        assert listar(client, outro).json() == []
        assert listar(client, outro).headers["X-Total-Count"] == "0"
        assert nao_lidas(client, outro) == 0


def test_dev_so_ve_as_proprias(client, usuario_no_banco, pessoas):
    dev = usuario_no_banco(papel="DEV", senha=None)
    criar([dev, pessoas[0]], chave="teste:dev")
    criar(pessoas[:1], chave="teste:so-dela")

    assert len(listar(client, dev).json()) == 1
    assert len(listar(client, pessoas[0]).json()) == 2


def test_marcar_a_de_outro_da_404_igual_a_inexistente_e_nao_altera(client, sql, pessoas):
    criar(pessoas[:1])
    [dela] = listar(client, pessoas[0]).json()

    alheia = client.post(
        f"{ROTA}/{dela['notificacao_id']}/lida", headers=com_token(pessoas[1]["id"])
    )
    inexistente = client.post(f"{ROTA}/{uuid4()}/lida", headers=com_token(pessoas[1]["id"]))

    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.json() == inexistente.json()
    assert linhas(sql, pessoas[0])[0]["lida_em"] is None


def test_marcar_todas_nao_toca_nas_dos_outros(client, sql, pessoas):
    criar(pessoas[:2])

    client.post(f"{ROTA}/lidas", headers=com_token(pessoas[1]["id"]))

    assert linhas(sql, pessoas[0])[0]["lida_em"] is None
    assert linhas(sql, pessoas[1])[0]["lida_em"] is not None


def test_id_invalido_da_422(client, pessoas):
    assert (
        client.post(f"{ROTA}/nao-e-uuid/lida", headers=com_token(pessoas[0]["id"])).status_code
        == 422
    )


def test_leituras_simultaneas_sao_consistentes(client, sql, pessoas):
    criar(pessoas[:1])
    [aviso] = listar(client, pessoas[0]).json()

    def marcar(_):
        return client.post(
            f"{ROTA}/{aviso['notificacao_id']}/lida", headers=com_token(pessoas[0]["id"])
        )

    with ThreadPoolExecutor(6) as pool:
        respostas = list(pool.map(marcar, range(6)))

    assert {r.status_code for r in respostas} == {200}
    assert len({r.json()["lida_em"] for r in respostas}) == 1
    assert nao_lidas(client, pessoas[0]) == 0


# --- Swagger ---


def test_swagger_documenta_as_rotas_e_os_erros(client):
    caminhos = client.get("/openapi.json").json()["paths"]
    assert {"get"} <= set(caminhos[ROTA])
    assert "post" in caminhos[f"{ROTA}/lidas"]
    assert "get" in caminhos[f"{ROTA}/nao-lidas/contagem"]
    marcar = caminhos[f"{ROTA}/{{notificacao_id}}/lida"]["post"]
    assert "404" in marcar["responses"] and "401" in marcar["responses"]
    parametros = {p["name"] for p in caminhos[ROTA]["get"]["parameters"]}
    assert {"lida", "tipo", "limite", "deslocamento"} <= parametros


# --- Compatibilidade com o RF33 ---

CAMPOS_RF33 = {
    "id",
    "hackathon_id",
    "equipe_id",
    "submissao_id",
    "aprovada",
    "mensagem",
    "canal",
    "status_envio",
    "enviado_em",
    "erro",
    "criado_em",
    "pareceres",
}


def test_resposta_do_rf33_continua_valida_e_ganha_so_campos_novos(client, sql, resultado):
    assert resultado.homologar(client, [resultado.propostas[0]]).status_code == 200
    lider = {
        "id": sql(
            "SELECT m.usuario_id AS id FROM membros_equipe m JOIN submissoes s"
            " ON s.equipe_id = m.equipe_id WHERE s.id = :s",
            s=resultado.propostas[1],
        )[0]["id"]
    }

    [item] = listar(client, lider).json()

    assert CAMPOS_RF33 <= set(item)
    assert set(item) - CAMPOS_RF33 == {
        "notificacao_id",
        "tipo",
        "titulo",
        "dados",
        "referencia",
        "lida_em",
    }
    antigo = sql("SELECT * FROM notificacoes_resultado WHERE usuario_id = :u", u=lider["id"])[0]
    assert item["id"] == str(antigo["id"])  # o id do RF33 é preservado
    assert item["notificacao_id"] != item["id"]
    assert item["tipo"] == "RESULTADO"
    assert item["aprovada"] is False and "NÃO foi aprovada" in item["mensagem"]
    assert (item["canal"], item["status_envio"]) == ("PLATAFORMA", "ENVIADO")
    assert item["enviado_em"] and item["erro"] is None
    assert len(item["pareceres"]) == 2
    assert set(item["pareceres"][0]) == {"parecer", "recomendacao"}
    assert item["referencia"]["tipo"] == "HOMOLOGACAO"
    assert item["dados"]["aprovada"] is False
    assert item["lida_em"] is None


def test_marcar_resultado_como_lido_pelo_notificacao_id_mantem_o_formato(client, sql, resultado):
    assert resultado.homologar(client, [resultado.propostas[0]]).status_code == 200
    lider = {
        "id": sql(
            "SELECT m.usuario_id AS id FROM membros_equipe m JOIN submissoes s"
            " ON s.equipe_id = m.equipe_id WHERE s.id = :s",
            s=resultado.propostas[0],
        )[0]["id"]
    }
    [item] = listar(client, lider).json()

    marcada = client.post(
        f"{ROTA}/{item['notificacao_id']}/lida", headers=com_token(lider["id"])
    ).json()

    assert CAMPOS_RF33 <= set(marcada)
    assert marcada["id"] == item["id"] and marcada["lida_em"]
    assert len(marcada["pareceres"]) == 2
    # O id do RF33 não é o da central: usá-lo na rota de leitura não acha nada
    assert (
        client.post(f"{ROTA}/{item['id']}/lida", headers=com_token(lider["id"])).status_code == 404
    )


def test_resultado_convive_com_os_demais_tipos_na_mesma_lista(client, sql, resultado):
    assert resultado.homologar(client, [resultado.propostas[0]]).status_code == 200
    lider_id = sql(
        "SELECT m.usuario_id AS id FROM membros_equipe m JOIN submissoes s"
        " ON s.equipe_id = m.equipe_id WHERE s.id = :s",
        s=resultado.propostas[0],
    )[0]["id"]
    criar([{"id": lider_id}], TipoNotificacao.CHAT, "chat:1")

    itens = listar(client, {"id": lider_id}).json()

    assert sorted(i["tipo"] for i in itens) == ["CHAT", "RESULTADO"]
    assert listar(client, {"id": lider_id}, tipo="RESULTADO").headers["X-Total-Count"] == "1"


# --- Integração com os fluxos existentes ---


def avisos(sql, usuario, tipo=None):
    return [a for a in linhas(sql, usuario) if tipo is None or a["tipo"] == tipo]


def test_convite_avisa_quem_ja_tem_conta_e_o_email_continua(client, sql, inscricao):
    convidado = inscricao.usuario_no_banco(senha=None)

    resposta = inscricao.convidar(client, email=convidado["email"])

    assert resposta.status_code == 201
    [aviso] = avisos(sql, convidado)
    assert aviso["tipo"] == "CONVITE"
    assert aviso["chave_idempotencia"] == f"convite:{resposta.json()['id']}"
    assert aviso["referencia_tipo"] == "CONVITE"
    assert str(aviso["referencia_id"]) == resposta.json()["id"]
    assert sql("SELECT 1 FROM emails_outbox WHERE tipo = 'CONVITE_EQUIPE'")  # e-mail intocado
    assert avisos(sql, inscricao.lider) == []


def test_convite_a_quem_nao_tem_conta_so_gera_email(client, sql, inscricao):
    assert inscricao.convidar(client, email=inscricao.novo_email()).status_code == 201
    assert sql("SELECT 1 FROM notificacoes") == []


@pytest.mark.parametrize("acao,resposta", [("aceitar", "ACEITO"), ("recusar", "RECUSADO")])
def test_resposta_ao_convite_avisa_o_lider(client, sql, inscricao, acao, resposta):
    convidado, convite_id = inscricao.convidar_usuario(client)

    assert getattr(inscricao, acao)(client, convidado, convite_id).status_code == 200

    [aviso] = avisos(sql, inscricao.lider, "ACEITE")
    assert aviso["dados"]["resposta"] == resposta
    assert aviso["chave_idempotencia"] == f"convite-resposta:{convite_id}:{resposta}"
    assert str(aviso["referencia_id"]) == convite_id
    # Repetir a resposta é recusado e não duplica o aviso
    assert getattr(inscricao, acao)(client, convidado, convite_id).status_code == 409
    assert len(avisos(sql, inscricao.lider, "ACEITE")) == 1


def test_resposta_recusada_pelas_regras_nao_avisa(client, sql, inscricao):
    convidado, convite_id = inscricao.convidar_usuario(client)
    inscricao.definir_status("INSCRICOES_ENCERRADAS")

    assert inscricao.aceitar(client, convidado, convite_id).status_code == 409
    assert avisos(sql, inscricao.lider, "ACEITE") == []


def test_falha_ao_notificar_nao_derruba_o_convite_nem_o_email(client, sql, inscricao, monkeypatch):
    async def quebrar(*_, **__):
        raise RuntimeError("banco indisponível para notificações")

    monkeypatch.setattr("app.services.notificacao.inserir_ignorando_repetidas", quebrar)
    convidado = inscricao.usuario_no_banco(senha=None)

    resposta = inscricao.convidar(client, email=convidado["email"])

    assert resposta.status_code == 201
    assert sql("SELECT 1 FROM notificacoes") == []
    assert sql("SELECT 1 FROM emails_outbox WHERE tipo = 'CONVITE_EQUIPE'")
    meus = client.get("/convites/meus", headers=com_token(convidado["id"])).json()
    assert [c["id"] for c in meus] == [resposta.json()["id"]]


def test_falha_ao_notificar_a_resposta_nao_desfaz_o_aceite(client, sql, inscricao, monkeypatch):
    convidado, convite_id = inscricao.convidar_usuario(client)

    async def quebrar(*_, **__):
        raise RuntimeError("falha ao notificar")

    monkeypatch.setattr("app.services.notificacao.inserir_ignorando_repetidas", quebrar)

    assert inscricao.aceitar(client, convidado, convite_id).status_code == 200
    assert sql(
        "SELECT 1 FROM membros_equipe WHERE usuario_id = :u AND equipe_id = :e",
        u=convidado["id"],
        e=inscricao.equipe_id,
    )


def test_inscricao_concluida_avisa_cada_integrante(client, sql, inscricao):
    pessoas = inscricao.montar(client)

    assert inscricao.concluir(client).status_code == 200

    protocolo = inscricao.protocolos()[0]
    for pessoa in pessoas:
        [aviso] = avisos(sql, pessoa, "INSCRICAO")
        assert aviso["chave_idempotencia"] == f"inscricao:{protocolo['id']}"
        assert protocolo["numero"] in aviso["mensagem"]
        assert aviso["dados"]["evento"] == "CONCLUIDA"


def test_equipe_homologada_avisa_uma_vez_cada_integrante(client, sql, inscricao):
    pessoas = inscricao.montar(client, vinculos=True)

    assert inscricao.concluir(client).json()["situacao"] == "HOMOLOGADA"

    for pessoa in pessoas:
        eventos = sorted(a["dados"]["evento"] for a in avisos(sql, pessoa, "INSCRICAO"))
        assert eventos == ["CONCLUIDA", "HOMOLOGADA"]
    organizador = inscricao.usuario_no_banco(papel="ORGANIZADOR", senha=None)
    reavaliar = client.post(
        f"/admin/hackathons/{inscricao.hackathon_id}/equipes/reavaliar",
        headers=com_token(organizador["id"]),
    )
    assert reavaliar.status_code == 200
    assert len(avisos(sql, pessoas[0], "INSCRICAO")) == 2  # nada repetido


def test_conclusao_recusada_nao_avisa(client, sql, inscricao):
    pessoas = inscricao.montar(client)

    assert inscricao.concluir(client, quem=pessoas[1]).status_code == 403
    assert sql("SELECT 1 FROM notificacoes WHERE tipo = 'INSCRICAO'") == []


def test_envio_da_proposta_avisa_so_o_lider(client, sql, envio):
    envio.preparar(client)
    integrante = envio.integrante()

    resposta = envio.enviar(client)

    assert resposta.status_code == 200, resposta.text
    numero = resposta.json()["protocolo"]["numero"]
    [aviso] = avisos(sql, envio.lider)
    assert aviso["tipo"] == "PROPOSTA" and numero in aviso["mensagem"]
    assert aviso["chave_idempotencia"] == f"protocolo_proposta:{resposta.json()['protocolo']['id']}"
    assert avisos(sql, integrante) == []
    assert envio.enviar(client).status_code == 409
    assert len(avisos(sql, envio.lider)) == 1


def test_resultado_cria_a_central_junto_do_rf33_para_todos(client, sql, resultado):
    assert resultado.homologar(client, [resultado.propostas[0]]).status_code == 200

    pares = sql(
        "SELECT r.id AS rf33, n.id AS central, n.usuario_id = r.usuario_id AS mesmo_usuario,"
        " n.lida_em, n.chave_idempotencia, r.equipe_id, r.homologacao_id"
        " FROM notificacoes_resultado r JOIN notificacoes n ON n.notificacao_resultado_id = r.id"
        " WHERE r.hackathon_id = :h",
        h=resultado.hackathon_id,
    )
    total_rf33 = sql(
        "SELECT count(*) AS n FROM notificacoes_resultado WHERE hackathon_id = :h",
        h=resultado.hackathon_id,
    )[0]["n"]
    assert total_rf33 == len(pares) == 3
    for par in pares:
        assert par["mesmo_usuario"] and par["lida_em"] is None
        assert par["chave_idempotencia"] == f"resultado:{par['homologacao_id']}:{par['equipe_id']}"


# --- Mentoria (RF53): o evento passa a ser publicado na central ---


def test_atribuicao_de_mentor_notifica_equipe_e_mentor_na_central(client, sql, cenario_mentoria):
    s = cenario_mentoria
    mentor, membro = s.mentor(), s.membro()

    resposta = atribuir(client, s, mentor)

    assert resposta.status_code == 201
    atribuicao_id = resposta.json()["id"]
    for usuario in (mentor, membro):
        [aviso] = avisos(sql, usuario)
        assert aviso["tipo"] == "MENTOR"
        assert aviso["chave_idempotencia"] == f"mentoria:{atribuicao_id}:ATRIBUIDA"
        assert aviso["dados"]["evento"] == "ATRIBUIDA"
        assert str(aviso["referencia_id"]) == atribuicao_id
    eventos = sql(
        "SELECT * FROM eventos_notificacao_mentoria WHERE atribuicao_id = :a", a=atribuicao_id
    )
    assert eventos and all(e["publicado_na_plataforma_em"] is not None for e in eventos)
    assert listar(client, membro).json()[0]["tipo"] == "MENTOR"


def test_substituicao_notifica_o_mentor_anterior(client, sql, cenario_mentoria):
    s = cenario_mentoria
    antigo, novo, membro = s.mentor(), s.mentor(), s.membro()
    inicial = atribuir(client, s, antigo).json()

    assert substituir(client, s, novo, inicial).status_code == 200

    for usuario in (antigo, novo, membro):
        assert {a["dados"]["evento"] for a in avisos(sql, usuario)} >= {"SUBSTITUIDA"}
    assert len(avisos(sql, antigo)) == 2  # atribuído e depois substituído


def test_falha_ao_publicar_deixa_o_evento_pendente_e_mantem_a_atribuicao(
    client, sql, cenario_mentoria, monkeypatch
):
    s = cenario_mentoria

    async def falhou(*_, **__):
        return None

    monkeypatch.setattr("app.services.notificacao_mentoria.notificar", falhou)

    resposta = atribuir(client, s, s.mentor())

    assert resposta.status_code == 201
    eventos = sql(
        "SELECT * FROM eventos_notificacao_mentoria WHERE atribuicao_id = :a",
        a=resposta.json()["id"],
    )
    assert eventos and all(e["publicado_na_plataforma_em"] is None for e in eventos)


# --- Migration: histórico entra como lido ---


def _backfill_da_migration() -> str:
    sql_migration = Path("migrations/V202611161200__central_notificacoes.sql").read_text(
        encoding="utf-8"
    )
    return sql_migration[sql_migration.index("-- Histórico do RF33") :]


def test_backfill_traz_o_historico_como_lido(client, sql, resultado, cenario_mentoria):
    """Reaplica os INSERTs da migration sobre dados que já existiam antes da central."""
    assert resultado.homologar(client, [resultado.propostas[0]]).status_code == 200
    s = cenario_mentoria
    s.membro()
    resposta = atribuir(client, s, s.mentor())
    assert resposta.status_code == 201
    atribuicao_id = resposta.json()["id"]
    sql("DELETE FROM notificacoes")
    sql(
        "UPDATE eventos_notificacao_mentoria SET publicado_na_plataforma_em = NULL"
        " WHERE atribuicao_id = :a",
        a=atribuicao_id,
    )

    for comando in filter(None, (c.strip() for c in _backfill_da_migration().split(";\n"))):
        sql(comando.rstrip(";"))

    resultados = sql("SELECT * FROM notificacoes WHERE tipo = 'RESULTADO'")
    mentoria = sql("SELECT * FROM notificacoes WHERE tipo = 'MENTOR'")
    assert len(resultados) == 3 and len(mentoria) == 2
    for aviso in resultados + mentoria:
        assert aviso["lida_em"] == aviso["criado_em"]  # entram lidas: o contador não infla
    assert all(r["notificacao_resultado_id"] is not None for r in resultados)
    assert all(m["chave_idempotencia"] == f"mentoria:{atribuicao_id}:ATRIBUIDA" for m in mentoria)
    assert (
        sql(
            "SELECT 1 FROM eventos_notificacao_mentoria WHERE atribuicao_id = :a"
            " AND publicado_na_plataforma_em IS NULL",
            a=atribuicao_id,
        )
        == []
    )
