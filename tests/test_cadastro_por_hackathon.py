"""BE-S6-14: seleção explícita, compatibilidade segura e isolamento entre edições."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest

from tests.test_auth import cadastrar
from tests.test_autodeclaracao import ESTUDANTE, PROFISSIONAL
from tests.test_cadastro_equipe_integrantes import CenarioFluxo
from tests.test_convites import com_token
from tests.test_organizacoes import DuasOrganizacoes

LINK = "https://example.com/comprovante.pdf"


@pytest.fixture
def edicoes(sql, usuario_no_banco, sem_edicoes_abertas):
    c = DuasOrganizacoes(sql, usuario_no_banco)
    c.hackathon_b = sql(
        "INSERT INTO hackathon (nome, status, organizacao_id, data_inicio)"
        " VALUES ('Hackathon B', 'INSCRICOES', :o, '2100-01-01') RETURNING id",
        o=c.org_b,
    )[0]["id"]
    # A é intencionalmente menos recente: um ID explícito deve prevalecer sobre datas.
    c.hackathons = [c.hackathon_a, c.hackathon_b]
    try:
        yield c
    finally:
        for h in c.hackathons:
            for tabela in ("protocolos", "convites", "aceites_termos"):
                if tabela == "aceites_termos":
                    sql(
                        "DELETE FROM aceites_termos WHERE termo_id IN"
                        " (SELECT id FROM termos WHERE hackathon_id = :h)",
                        h=h,
                    )
                else:
                    sql(
                        f"DELETE FROM {tabela} WHERE equipe_id IN"
                        " (SELECT id FROM equipes WHERE hackathon_id = :h)",
                        h=h,
                    )
            for tabela in (
                "comprovantes_vinculo",
                "autodeclaracoes_vinculo",
                "membros_equipe",
                "equipes",
                "termos",
            ):
                sql(f"DELETE FROM {tabela} WHERE hackathon_id = :h", h=h)
        c.limpar()


def declarar(client, pessoa, h, corpo=ESTUDANTE):
    return client.put(
        "/me/autodeclaracao",
        params={"hackathon_id": str(h)},
        headers=com_token(pessoa["id"]),
        json=corpo,
    )


def consultar(client, pessoa, h):
    return client.get(
        "/me/autodeclaracao", params={"hackathon_id": str(h)}, headers=com_token(pessoa["id"])
    )


def enviar(client, pessoa, h, url=LINK, **extra):
    return client.post(
        "/comprovantes",
        headers=com_token(pessoa["id"]),
        json={"hackathon_id": str(h), "arquivo_url": url, **extra},
    )


@pytest.fixture
def equipes(client, sql, edicoes, usuario_no_banco):
    """As mesmas três pessoas em equipes de duas organizações, com termos próprios aceitos."""
    pessoas = [usuario_no_banco() for _ in range(3)]
    times = []
    for h in edicoes.hackathons:
        termos = [
            str(
                sql(
                    "INSERT INTO termos (hackathon_id, tipo, versao, titulo, conteudo, vigente)"
                    " VALUES (:h, CAST(:t AS tipo_termo), '1', 'Termo', 'Texto', true)"
                    " RETURNING id",
                    h=h,
                    t=tipo,
                )[0]["id"]
            )
            for tipo in ("REGULAMENTO", "TERMO_CONSENTIMENTO")
        ]
        resposta = client.post(
            "/equipes",
            headers=com_token(pessoas[0]["id"]),
            json={
                "hackathon_id": str(h),
                "integrantes": [{"nome": "Integrante", "email": p["email"]} for p in pessoas[1:]],
            },
        )
        assert resposta.status_code == 201, resposta.text
        time = resposta.json()["id"]
        for p in pessoas[1:]:
            [convite] = sql(
                "SELECT id FROM convites WHERE equipe_id = :e AND email = :m", e=time, m=p["email"]
            )
            aceite = client.post(
                f"/convites/{convite['id']}/aceitar",
                headers=com_token(p["id"]),
                json={"termos_ids": termos},
            )
            assert aceite.status_code == 200, aceite.text
        assert (
            client.post(
                f"/hackathons/{h}/termos/aceites",
                headers=com_token(pessoas[0]["id"]),
                json={"termos_ids": termos},
            ).status_code
            == 201
        )
        times.append(time)
    return pessoas, times


def situacoes(sql, times):
    return [
        sql("SELECT situacao::text FROM equipes WHERE id = :e", e=t)[0]["situacao"] for t in times
    ]


def aprovar(client, doc, gestor):
    return client.post(f"/admin/comprovantes/{doc['id']}/aprovar", headers=com_token(gestor["id"]))


def test_aprovacao_nao_comprova_nem_homologa_outra_edicao(client, sql, edicoes, equipes):
    pessoas, times = equipes
    pendentes = []
    for h, time, gestor in zip(
        edicoes.hackathons, times, [edicoes.org_a_comite, edicoes.org_b_comite], strict=True
    ):
        for p in pessoas:
            envio = enviar(client, p, h)
            assert envio.status_code == 201, envio.text
            if p == pessoas[1]:
                pendentes.append(envio.json())
            else:
                assert aprovar(client, envio.json(), gestor).status_code == 200
        conclusao = client.post(
            f"/equipes/{time}/inscricao/concluir", headers=com_token(pessoas[0]["id"])
        )
        assert conclusao.status_code == 200, conclusao.text
    assert situacoes(sql, times) == ["AGUARDANDO_HOMOLOGACAO"] * 2
    assert aprovar(client, pendentes[0], edicoes.org_a_comite).status_code == 200
    assert situacoes(sql, times) == ["HOMOLOGADA", "AGUARDANDO_HOMOLOGACAO"]
    assert consultar(client, pessoas[1], edicoes.hackathon_a).json()["vinculo_comprovado"] is True
    assert consultar(client, pessoas[1], edicoes.hackathon_b).json()["vinculo_comprovado"] is False
    # Mesmo reavaliando a outra edição, a conta global ATIVA não substitui o documento local.
    reavaliacao = client.post(
        f"/admin/hackathons/{edicoes.hackathon_b}/equipes/reavaliar",
        headers=com_token(edicoes.org_b_organizador["id"]),
    )
    assert reavaliacao.status_code == 200
    assert situacoes(sql, times) == ["HOMOLOGADA", "AGUARDANDO_HOMOLOGACAO"]
    assert aprovar(client, pendentes[1], edicoes.org_b_comite).status_code == 200
    assert situacoes(sql, times) == ["HOMOLOGADA"] * 2


def test_declaracao_divergente_so_retira_homologacao_da_edicao_escolhida(
    client, sql, edicoes, equipes
):
    pessoas, times = equipes
    for h, time, gestor in zip(
        edicoes.hackathons, times, [edicoes.org_a_comite, edicoes.org_b_comite], strict=True
    ):
        for p in pessoas:
            assert declarar(client, p, h).status_code == 200
            assert aprovar(client, enviar(client, p, h).json(), gestor).status_code == 200
        assert (
            client.post(
                f"/equipes/{time}/inscricao/concluir", headers=com_token(pessoas[0]["id"])
            ).status_code
            == 200
        )
    assert situacoes(sql, times) == ["HOMOLOGADA"] * 2
    assert declarar(client, pessoas[1], edicoes.hackathon_a, PROFISSIONAL).status_code == 200
    assert situacoes(sql, times) == ["AGUARDANDO_HOMOLOGACAO", "HOMOLOGADA"]
    assert consultar(client, pessoas[1], edicoes.hackathon_b).json()["atual"]["tipo"] == "ESTUDANTE"


@pytest.mark.parametrize("edicao", ["hackathon_a", "hackathon_b"])
def test_cadastro_explicito_usa_edicao_escolhida(client, sql, edicoes, novo_email, edicao):
    h = getattr(edicoes, edicao)
    resposta = cadastrar(client, novo_email(), hackathon_id=str(h))
    assert resposta.status_code == 201, resposta.text
    [comprovante] = sql(
        "SELECT hackathon_id, tipo_vinculo::text, status::text FROM comprovantes_vinculo"
        " WHERE usuario_id = :u",
        u=resposta.json()["id"],
    )
    assert comprovante == {"hackathon_id": h, "tipo_vinculo": "ESTUDANTE", "status": "PENDENTE"}


def test_fluxos_sem_id_recusam_ambiguidade_sem_gravar(
    client, sql, edicoes, novo_email, usuario_no_banco
):
    pessoa, email = usuario_no_banco(situacao_conta="PENDENTE"), novo_email()
    respostas = [
        cadastrar(client, email),
        client.get("/me/autodeclaracao", headers=com_token(pessoa["id"])),
        client.put("/me/autodeclaracao", headers=com_token(pessoa["id"]), json=ESTUDANTE),
        client.post("/comprovantes", headers=com_token(pessoa["id"]), json={"arquivo_url": LINK}),
    ]
    for resposta in respostas:
        assert resposta.status_code == 409, resposta.text
        assert "hackathon_id" in resposta.json()["detail"]
    assert sql("SELECT id FROM usuarios WHERE email = :e", e=email) == []
    for tabela in ("autodeclaracoes_vinculo", "comprovantes_vinculo"):
        assert sql(f"SELECT id FROM {tabela} WHERE usuario_id = :u", u=pessoa["id"]) == []


@pytest.mark.parametrize(
    "estado,codigo",
    [
        ("inexistente", 404),
        ("CANCELADO", 409),
        ("RASCUNHO", 409),
        ("INSCRICOES_ENCERRADAS", 409),
        ("prazo-encerrado", 409),
        ("inicio-futuro", 409),
    ],
)
def test_escritas_validam_id_status_e_periodo_sem_fallback(
    client, sql, edicoes, novo_email, usuario_no_banco, estado, codigo
):
    h = edicoes.hackathon_a
    if estado == "inexistente":
        h = uuid4()
    elif estado in ("prazo-encerrado", "inicio-futuro"):
        campo, intervalo = (
            ("inscricoes_fim", timedelta(days=-1))
            if estado == "prazo-encerrado"
            else ("inscricoes_inicio", timedelta(days=1))
        )
        sql(
            f"UPDATE hackathon SET {campo} = now() + CAST(:i AS interval) WHERE id = :h",
            i=intervalo,
            h=h,
        )
    else:
        sql(
            "UPDATE hackathon SET status = CAST(:s AS status_hackathon) WHERE id = :h",
            s=estado,
            h=h,
        )
    pessoa, email = usuario_no_banco(), novo_email()
    for resposta in (
        cadastrar(client, email, hackathon_id=str(h)),
        declarar(client, pessoa, h),
        enviar(client, pessoa, h),
    ):
        assert resposta.status_code == codigo, resposta.text
    assert sql("SELECT id FROM usuarios WHERE email = :e", e=email) == []
    assert sql("SELECT id FROM comprovantes_vinculo WHERE usuario_id = :u", u=pessoa["id"]) == []
    assert sql("SELECT id FROM autodeclaracoes_vinculo WHERE usuario_id = :u", u=pessoa["id"]) == []


def test_declaracoes_historico_e_comprovantes_ficam_na_edicao(client, edicoes, usuario_no_banco):
    pessoa = usuario_no_banco(situacao_conta="PENDENTE")
    a, b = edicoes.hackathons
    assert declarar(client, pessoa, a).status_code == 200
    assert declarar(client, pessoa, a, {**ESTUDANTE, "periodo": 6}).status_code == 200
    assert declarar(client, pessoa, b, PROFISSIONAL).status_code == 200
    ca = enviar(client, pessoa, a, "https://example.com/a.pdf")
    cb = enviar(client, pessoa, b, "https://example.com/b.pdf")
    assert (ca.status_code, cb.status_code) == (201, 201)
    sa, sb = consultar(client, pessoa, a).json(), consultar(client, pessoa, b).json()
    assert [d["periodo"] for d in sa["historico"]] == [6, 5]
    assert [d["tipo"] for d in sb["historico"]] == ["PROFISSIONAL"]
    for situacao, comprovante, tipo, h in (
        (sa, ca.json(), "ESTUDANTE", a),
        (sb, cb.json(), "PROFISSIONAL", b),
    ):
        assert situacao["comprovante"]["id"] == comprovante["id"]
        assert comprovante["tipo_vinculo"] == tipo
        assert comprovante["autodeclaracao_id"] == situacao["atual"]["id"]
        assert all(d["hackathon_id"] == str(h) for d in situacao["historico"])
        assert "arquivo_url" not in str(situacao)
    meus = client.get("/comprovantes/meus", headers=com_token(pessoa["id"])).json()
    assert {c["hackathon_id"] for c in meus} == {str(a), str(b)}


@pytest.mark.parametrize("estado", ["INSCRICOES_ENCERRADAS", "FINALIZADO", "CANCELADO"])
def test_consulta_historica_explicita_nao_reabre_prazo(
    client, sql, edicoes, usuario_no_banco, estado
):
    pessoa, h = usuario_no_banco(), edicoes.hackathon_a
    antes = declarar(client, pessoa, h).json()
    sql("UPDATE hackathon SET status = CAST(:s AS status_hackathon) WHERE id = :h", s=estado, h=h)
    consulta = consultar(client, pessoa, h)
    assert consulta.status_code == 200
    assert consulta.json()["atual"] == antes
    assert declarar(client, pessoa, h, PROFISSIONAL).status_code == 409
    assert enviar(client, pessoa, h).status_code == 409
    assert consultar(client, pessoa, h).json()["historico"] == [antes]


def test_consulta_id_inexistente_e_rascunho(client, sql, edicoes, usuario_no_banco):
    pessoa = usuario_no_banco()
    assert consultar(client, pessoa, uuid4()).status_code == 404
    sql("UPDATE hackathon SET status = 'RASCUNHO' WHERE id = :h", h=edicoes.hackathon_a)
    assert consultar(client, pessoa, edicoes.hackathon_a).status_code == 404


def test_id_da_edicao_nao_da_acesso_a_dados_de_terceiros(client, edicoes, usuario_no_banco):
    dono, outro = usuario_no_banco(), usuario_no_banco()
    h = edicoes.hackathon_a
    assert declarar(client, dono, h).status_code == 200
    doc = enviar(client, dono, h).json()
    consulta = consultar(client, outro, h).json()
    assert consulta["atual"] is None and consulta["historico"] == []
    assert consulta["comprovante"] is None
    assert client.get("/comprovantes/meus", headers=com_token(outro["id"])).json() == []
    assert (
        declarar(client, outro, h, {**ESTUDANTE, "usuario_id": str(dono["id"])}).status_code == 422
    )
    # Campos extras antigos no comprovante são ignorados; o dono continua vindo do token.
    proprio = enviar(client, outro, h, usuario_id=str(dono["id"]))
    assert proprio.status_code == 201
    assert proprio.json()["usuario_id"] == str(outro["id"])
    assert proprio.json()["id"] != doc["id"]
    assert (
        client.post(
            f"/admin/comprovantes/{doc['id']}/aprovar", headers=com_token(outro["id"])
        ).status_code
        == 403
    )


@pytest.mark.parametrize("acao", ["aprovar", "recusar"])
def test_organizacao_so_valida_sua_edicao_e_dev_preserva_excecao(
    client, sql, edicoes, usuario_no_banco, acao
):
    pessoa = usuario_no_banco()
    docs = [enviar(client, pessoa, h).json() for h in edicoes.hackathons]
    for gestor, esperado in ((edicoes.org_a_comite, docs[0]), (edicoes.org_b_organizador, docs[1])):
        fila = client.get("/admin/comprovantes", headers=com_token(gestor["id"])).json()
        assert [item["id"] for item in fila] == [esperado["id"]]
    corpo = {"motivo_recusa": "Ilegível"} if acao == "recusar" else None
    resposta = client.post(
        f"/admin/comprovantes/{docs[0]['id']}/{acao}",
        json=corpo,
        headers=com_token(edicoes.org_b_comite["id"]),
    )
    assert resposta.status_code == 403
    assert (
        sql("SELECT status::text FROM comprovantes_vinculo WHERE id = :i", i=docs[0]["id"])[0][
            "status"
        ]
        == "PENDENTE"
    )
    dev = usuario_no_banco(papel="DEV")
    assert (
        client.post(
            f"/admin/comprovantes/{docs[0]['id']}/{acao}", json=corpo, headers=com_token(dev["id"])
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/admin/comprovantes/{uuid4()}/{acao}", json=corpo, headers=com_token(dev["id"])
        ).status_code
        == 404
    )


def test_cliente_legado_com_uma_edicao_usa_a_unica_e_nao_a_mais_recente(
    client, sql, edicoes, novo_email
):
    sql(
        "UPDATE hackathon SET inscricoes_inicio = now() + interval '1 day' WHERE id = :h",
        h=edicoes.hackathon_b,
    )
    cadastro = cadastrar(client, novo_email())
    assert cadastro.status_code == 201
    pessoa = cadastro.json()
    # Recusa do inicial permite reenviar no contrato legado.
    sql(
        "UPDATE comprovantes_vinculo SET status = 'RECUSADO', motivo_recusa = 'Ilegível',"
        " validado_em = now() WHERE usuario_id = :u",
        u=pessoa["id"],
    )
    assert (
        client.put(
            "/me/autodeclaracao", headers=com_token(pessoa["id"]), json=ESTUDANTE
        ).status_code
        == 200
    )
    consulta = client.get("/me/autodeclaracao", headers=com_token(pessoa["id"]))
    envio = client.post(
        "/comprovantes", headers=com_token(pessoa["id"]), json={"arquivo_url": LINK}
    )
    assert (consulta.status_code, envio.status_code) == (200, 201)
    assert (
        consulta.json()["hackathon_id"] == envio.json()["hackathon_id"] == str(edicoes.hackathon_a)
    )


@pytest.mark.parametrize(
    "etapa", ["criar_comprovante", "associar_convites_pendentes", "enviar_confirmacao"]
)
def test_falha_no_cadastro_reverte_conta_comprovante_e_registros(
    client, sql, edicoes, novo_email, usuario_no_banco, monkeypatch, etapa
):
    from app.services import auth

    original = getattr(auth, etapa)

    async def falhar(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("Falha induzida depois de persistir")

    monkeypatch.setattr(auth, etapa, falhar)
    email = novo_email()
    lider = usuario_no_banco()
    [equipe] = sql(
        "INSERT INTO equipes (hackathon_id, nome) VALUES (:h, 'Rollback') RETURNING id",
        h=edicoes.hackathon_a,
    )
    [convite] = sql(
        "INSERT INTO convites (equipe_id, nome, email, convidado_por)"
        " VALUES (:e, 'Convidada', :m, :u) RETURNING id",
        e=equipe["id"],
        m=email,
        u=lider["id"],
    )
    with pytest.raises(RuntimeError, match="Falha induzida"):
        cadastrar(client, email, hackathon_id=str(edicoes.hackathon_a))
    assert sql("SELECT id FROM usuarios WHERE email = :e", e=email) == []
    assert sql("SELECT id FROM emails_outbox WHERE destinatario_email = :e", e=email) == []
    assert (
        sql("SELECT id FROM comprovantes_vinculo WHERE hackathon_id = :h", h=edicoes.hackathon_a)
        == []
    )
    assert (
        sql("SELECT usuario_id FROM convites WHERE id = :c", c=convite["id"])[0]["usuario_id"]
        is None
    )
    monkeypatch.setattr(auth, etapa, original)
    cadastro = cadastrar(client, email, hackathon_id=str(edicoes.hackathon_a))
    assert cadastro.status_code == 201
    assert (
        str(sql("SELECT usuario_id FROM convites WHERE id = :c", c=convite["id"])[0]["usuario_id"])
        == cadastro.json()["id"]
    )
    assert (
        len(sql("SELECT id FROM notificacoes WHERE usuario_id = :u", u=cadastro.json()["id"])) == 1
    )


def test_sem_edicoes_abertas_preserva_409_nos_quatro_contratos(
    client, edicoes, sql, usuario_no_banco, novo_email
):
    sql(
        "UPDATE hackathon SET status = 'INSCRICOES_ENCERRADAS' WHERE id = ANY(:hs)",
        hs=edicoes.hackathons,
    )
    pessoa = usuario_no_banco()
    for resposta in (
        cadastrar(client, novo_email()),
        client.get("/me/autodeclaracao", headers=com_token(pessoa["id"])),
        client.put("/me/autodeclaracao", headers=com_token(pessoa["id"]), json=ESTUDANTE),
        client.post("/comprovantes", headers=com_token(pessoa["id"]), json={"arquivo_url": LINK}),
    ):
        assert resposta.status_code == 409
        assert resposta.json() == {"detail": "Não há hackathon com inscrições abertas no momento."}


def test_email_existente_nao_cria_conta_nem_comprovante_em_outra_edicao(
    client, sql, edicoes, novo_email
):
    email = novo_email()
    cadastro = cadastrar(client, email, hackathon_id=str(edicoes.hackathon_a))
    assert cadastro.status_code == 201
    assert (
        cadastrar(client, email.upper(), hackathon_id=str(edicoes.hackathon_b)).status_code == 409
    )
    assert (
        sql("SELECT id FROM comprovantes_vinculo WHERE hackathon_id = :h", h=edicoes.hackathon_b)
        == []
    )


def test_consulta_historica_respeita_prazo_encerrado_mesmo_com_status_inscricoes(
    client, sql, edicoes, usuario_no_banco
):
    pessoa, h = usuario_no_banco(), edicoes.hackathon_a
    declaracao = declarar(client, pessoa, h).json()
    sql("UPDATE hackathon SET inscricoes_fim = now() - interval '1 minute' WHERE id = :h", h=h)
    assert consultar(client, pessoa, h).json()["atual"] == declaracao
    assert declarar(client, pessoa, h, PROFISSIONAL).status_code == 409


def test_cadastros_concorrentes_em_edicoes_diferentes_nao_duplicam_conta(
    client, sql, edicoes, novo_email
):
    email = novo_email()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [
            pool.submit(cadastrar, client, e, hackathon_id=str(h))
            for e, h in zip((email, email.upper()), edicoes.hackathons, strict=True)
        ]
        respostas = [f.result() for f in futuros]
    assert sorted(r.status_code for r in respostas) == [201, 409]
    [pessoa] = sql("SELECT id FROM usuarios WHERE lower(email) = :e", e=email)
    [doc] = sql(
        "SELECT hackathon_id FROM comprovantes_vinculo WHERE usuario_id = :u", u=pessoa["id"]
    )
    vencedor = next(i for i, r in enumerate(respostas) if r.status_code == 201)
    assert doc["hackathon_id"] == edicoes.hackathons[vencedor]
    assert len(sql("SELECT id FROM emails_outbox WHERE destinatario_email = :e", e=email)) == 1


def test_comprovantes_concorrentes_respeitam_unicidade_por_edicao(
    client, sql, edicoes, usuario_no_banco
):
    pessoa = usuario_no_banco()
    a, b = edicoes.hackathons
    with ThreadPoolExecutor(max_workers=3) as pool:
        futuros = [pool.submit(enviar, client, pessoa, h) for h in (a, a, b)]
        respostas = [f.result().status_code for f in futuros]
    assert sorted(respostas[:2]) == [201, 409] and respostas[2] == 201
    assert (
        len(sql("SELECT id FROM comprovantes_vinculo WHERE usuario_id = :u", u=pessoa["id"])) == 2
    )


def test_declaracoes_concorrentes_nao_deduplicam_entre_edicoes(
    client, sql, edicoes, usuario_no_banco
):
    pessoa = usuario_no_banco()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futuros = [
            pool.submit(declarar, client, pessoa, h)
            for h in (edicoes.hackathon_a, edicoes.hackathon_a, edicoes.hackathon_b)
        ]
        assert [f.result().status_code for f in futuros] == [200, 200, 200]
    assert (
        len(sql("SELECT id FROM autodeclaracoes_vinculo WHERE usuario_id = :u", u=pessoa["id"]))
        == 2
    )


@pytest.mark.parametrize("tipo", ["ESTUDANTE", "PROFISSIONAL"])
def test_cadastro_por_convite_ignora_outras_edicoes_abertas(
    client, sql, edicoes, usuario_no_banco, novo_email, tipo
):
    fluxo = CenarioFluxo(sql, usuario_no_banco, novo_email)
    try:
        sql(
            "UPDATE hackathon SET organizacao_id = :o WHERE id = :h",
            o=edicoes.org_a,
            h=fluxo.hackathon_id,
        )
        equipe, novo, token = fluxo.equipe_com_novato(client)
        sql(
            "UPDATE convites SET tipo_integrante = CAST(:t AS tipo_integrante)"
            " WHERE equipe_id = :e AND email = :m",
            t=tipo,
            e=equipe["id"],
            m=novo["email"],
        )
        cadastro = fluxo.cadastrar(client, token, comprovante_url=LINK)
        assert cadastro.status_code == 201, cadastro.text
        [doc] = sql(
            "SELECT hackathon_id, tipo_vinculo::text FROM comprovantes_vinculo"
            " WHERE usuario_id = :u",
            u=cadastro.json()["id"],
        )
        assert doc == {"hackathon_id": fluxo.hackathon_id, "tipo_vinculo": tipo}
        assert fluxo.convite_de(equipe["id"], novo["email"])["status"] == "PENDENTE"
    finally:
        fluxo.limpar()


@pytest.mark.parametrize(
    "rota,metodo",
    [
        ("/auth/cadastro", "post"),
        ("/comprovantes", "post"),
        ("/me/autodeclaracao", "get"),
        ("/me/autodeclaracao", "put"),
    ],
)
def test_uuid_invalido_retorna_422(client, usuario_no_banco, novo_email, rota, metodo):
    pessoa = usuario_no_banco()
    if rota == "/auth/cadastro":
        resposta = cadastrar(client, novo_email(), hackathon_id="invalido")
    elif rota == "/comprovantes":
        resposta = enviar(client, pessoa, "invalido")
    else:
        kwargs = {"params": {"hackathon_id": "invalido"}, "headers": com_token(pessoa["id"])}
        if metodo == "put":
            kwargs["json"] = ESTUDANTE
        resposta = getattr(client, metodo)(rota, **kwargs)
    assert resposta.status_code == 422


def test_openapi_documenta_contratos_por_edicao(client):
    spec = client.get("/openapi.json").json()
    for metodo in ("get", "put"):
        rota = spec["paths"]["/me/autodeclaracao"][metodo]
        [param] = [p for p in rota["parameters"] if p["name"] == "hackathon_id"]
        assert param["in"] == "query" and param["required"] is False
        assert {"403", "404", "409", "422"} <= rota["responses"].keys()
    schemas = spec["components"]["schemas"]
    for nome in ("CadastroRequest", "ComprovanteEnvio"):
        assert "hackathon_id" in schemas[nome]["properties"]
        assert "hackathon_id" not in schemas[nome].get("required", [])
    assert "hackathon_id" not in schemas["AutodeclaracaoEnvio"]["properties"]
