"""BE-S5-11: atribuição, histórico, isolamento, capacidade e concorrência em PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.integrations.email import ProvedorMemoria
from app.security.token import criar_token
from tests.test_migrations import rodar
from tests.test_migrations import sql as sql_transacional


def headers(usuario):
    return {"Authorization": f"Bearer {criar_token(usuario['id'])}"}


@pytest.fixture
def s(sql, usuario_no_banco):
    cientifico = usuario_no_banco(papel="COMITE_CIENTIFICO", senha=None)
    organizador = usuario_no_banco(papel="ORGANIZADOR", senha=None)
    edicoes = []

    def edicao():
        h = sql("INSERT INTO hackathon(nome,status) VALUES ('Mentoria','ATIVO') RETURNING id")[0][
            "id"
        ]
        edicoes.append(h)
        termos = []
        for tipo in ("REGULAMENTO", "TERMO_CONSENTIMENTO"):
            termos.append(
                sql(
                    "INSERT INTO termos(hackathon_id,tipo,versao,titulo,conteudo,vigente)"
                    " VALUES(:h,CAST(:t AS tipo_termo),'1','Leia','Conteúdo',true) RETURNING id",
                    h=h,
                    t=tipo,
                )[0]["id"]
            )
        tema = sql(
            "INSERT INTO temas(hackathon_id,titulo,ativo) VALUES(:h,'Tema',true) RETURNING id", h=h
        )[0]["id"]
        homologacao = sql(
            "INSERT INTO homologacoes_resultado(hackathon_id,homologado_por,"
            "total_propostas,total_aprovadas)"
            " VALUES(:h,:u,3,2) RETURNING id",
            h=h,
            u=organizador["id"],
        )[0]["id"]
        equipes = []
        for n in range(3):
            equipe = sql(
                "INSERT INTO equipes(hackathon_id,nome,situacao)"
                " VALUES(:h,:nome,'HOMOLOGADA') RETURNING id",
                h=h,
                nome=f"Equipe {n}",
            )[0]["id"]
            equipes.append(equipe)
            proposta = sql(
                "INSERT INTO submissoes(equipe_id,hackathon_id,tema_id,status,titulo,"
                "descricao,ods,bases_dados,enviado_em)"
                " VALUES(:e,:h,:t,'ENVIADA','Proposta','Descrição','{1}','Base',now())"
                " RETURNING id",
                e=equipe,
                h=h,
                t=tema,
            )[0]["id"]
            sql(
                "INSERT INTO resultados_proposta(homologacao_id,hackathon_id,submissao_id,"
                "equipe_id,"
                "nota_media,classificacao,avaliacoes,recomendacoes_aprovacao,recomendacoes_reprovacao,aprovada)"
                " VALUES(:hom,:h,:p,:e,8,:n,2,2,0,:aprovada)",
                hom=homologacao,
                h=h,
                p=proposta,
                e=equipe,
                n=n + 1,
                aprovada=n < 2,
            )
        sql(
            "UPDATE hackathon SET treinamento_concluido_em=now(),"
            "treinamento_concluido_por=:u WHERE id=:h",
            h=h,
            u=organizador["id"],
        )
        return SimpleNamespace(h=h, termos=termos, equipes=equipes, homologacao=homologacao)

    primeira = edicao()

    def mentor(
        *, cap=2, ativo=True, concluido=True, aceites=True, ed=None, papel="MENTOR", senha=True
    ):
        ed = ed or primeira
        usuario = usuario_no_banco(papel=papel, ativo=ativo, senha="segredo123" if senha else None)
        sql(
            "UPDATE usuarios SET nome='Mentor Completo',empresa_parceira='Parceira',"
            "area_atuacao='Dados',"
            "max_equipes=:cap,mentor_perfil_concluido_em=CASE WHEN :ok THEN now() ELSE NULL END,"
            "mentor_ativado_em=CASE WHEN :ok THEN now() ELSE NULL END WHERE id=:u",
            cap=cap,
            ok=concluido,
            u=usuario["id"],
        )
        if aceites:
            for termo in ed.termos:
                sql(
                    "INSERT INTO aceites_termos(termo_id,usuario_id) VALUES(:t,:u)",
                    t=termo,
                    u=usuario["id"],
                )
        return usuario

    def membro(equipe=None, ed=None):
        ed = ed or primeira
        equipe = equipe or ed.equipes[0]
        usuario = usuario_no_banco(senha=None)
        sql(
            "INSERT INTO membros_equipe(equipe_id,hackathon_id,usuario_id,funcao)"
            " VALUES(:e,:h,:u,'DESENVOLVEDOR')",
            e=equipe,
            h=ed.h,
            u=usuario["id"],
        )
        return usuario

    yield SimpleNamespace(
        h=primeira.h,
        equipes=primeira.equipes,
        termos=primeira.termos,
        homologacao=primeira.homologacao,
        mentor=mentor,
        membro=membro,
        cientifico=cientifico,
        organizador=organizador,
        edicao=edicao,
    )
    sql(
        "DELETE FROM eventos_notificacao_mentoria WHERE atribuicao_id IN"
        " (SELECT id FROM atribuicoes_mentor WHERE hackathon_id=ANY(:hs))",
        hs=edicoes,
    )
    sql("DELETE FROM atribuicoes_mentor WHERE hackathon_id=ANY(:hs)", hs=edicoes)
    sql(
        "DELETE FROM aceites_termos WHERE termo_id IN"
        " (SELECT id FROM termos WHERE hackathon_id=ANY(:hs))",
        hs=edicoes,
    )
    for tabela in (
        "convites_mentor",
        "resultados_proposta",
        "homologacoes_resultado",
        "membros_equipe",
        "submissoes",
        "temas",
        "equipes",
        "termos",
    ):
        sql(f"DELETE FROM {tabela} WHERE hackathon_id=ANY(:hs)", hs=edicoes)
    sql("DELETE FROM hackathon WHERE id=ANY(:hs)", hs=edicoes)


def url(equipe):
    return f"/admin/equipes/{equipe}/mentoria"


def atribuir(client, s, mentor, equipe=None, quem=None, **extras):
    return client.post(
        url(equipe or s.equipes[0]),
        headers=headers(quem or s.cientifico),
        json={"mentor_id": str(mentor["id"]), **extras},
    )


def substituir(client, s, mentor, atual, equipe=None, **extras):
    return client.put(
        url(equipe or s.equipes[0]),
        headers=headers(s.cientifico),
        json={
            "mentor_id": str(mentor["id"]),
            "atribuicao_atual_id": atual["id"],
            "motivo": "Substituição administrativa",
            **extras,
        },
    )


@pytest.mark.parametrize("papel", ["COMITE_CIENTIFICO", "ORGANIZADOR", "DEV"])
def test_atribuir_autorizados_e_marcos(client, s, sql, usuario_no_banco, papel):
    mentor = s.mentor()
    ator = usuario_no_banco(papel=papel, senha=None)
    resposta = atribuir(client, s, mentor, quem=ator)
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["mentor_id"] == str(mentor["id"])
    assert dados["hackathon_id"] == str(s.h)
    assert dados["atribuido_por"] == str(ator["id"])
    assert dados["atribuido_em"] and dados["encerrada_em"] is None
    assert len(sql("SELECT 1 FROM atribuicoes_mentor WHERE equipe_id=:e", e=s.equipes[0])) == 1


@pytest.mark.parametrize(
    "tipo", ["treinamento", "reprovada", "sem_resultado", "CANCELADO", "FINALIZADO"]
)
def test_regras_da_equipe(client, s, sql, tipo):
    mentor = s.mentor()
    equipe = s.equipes[0]
    if tipo == "treinamento":
        sql(
            "UPDATE hackathon SET treinamento_concluido_em=NULL,"
            "treinamento_concluido_por=NULL WHERE id=:h",
            h=s.h,
        )
    elif tipo == "reprovada":
        equipe = s.equipes[2]
    elif tipo == "sem_resultado":
        sql("DELETE FROM resultados_proposta WHERE equipe_id=:e", e=equipe)
    else:
        sql("UPDATE hackathon SET status=CAST(:s AS status_hackathon) WHERE id=:h", h=s.h, s=tipo)
    assert atribuir(client, s, mentor, equipe).status_code == 409
    assert sql("SELECT 1 FROM atribuicoes_mentor WHERE equipe_id=:e", e=equipe) == []
    assert sql("SELECT 1 FROM emails_outbox WHERE tipo='ATRIBUICAO_MENTOR'") == []


@pytest.mark.parametrize(
    "campos",
    [
        {"ativo": False},
        {"concluido": False},
        {"aceites": False},
        {"senha": False},
        {"cap": None},
    ],
)
def test_mentor_inelegivel(client, s, campos):
    assert atribuir(client, s, s.mentor(**campos)).status_code == 409


def test_mentor_de_outra_edicao_e_termos_desatualizados(client, s, sql):
    outra = s.edicao()
    mentor = s.mentor(ed=outra)
    assert atribuir(client, s, mentor).status_code == 409
    mentor = s.mentor()
    sql("UPDATE termos SET vigente=false WHERE id=:t", t=s.termos[0])
    assert atribuir(client, s, mentor).status_code == 409


def test_capacidade_global_e_reducao(client, s):
    mentor = s.mentor(cap=1)
    assert atribuir(client, s, mentor).status_code == 201
    assert atribuir(client, s, mentor, s.equipes[1]).status_code == 409
    assert atribuir(client, s, mentor).status_code == 409
    assert (
        client.patch(
            f"/admin/mentores/{mentor['id']}",
            headers=headers(s.cientifico),
            json={"max_equipes": 1},
        ).status_code
        == 200
    )


def test_capacidade_entre_edicoes(client, s, sql):
    mentor = s.mentor(cap=1)
    outra = s.edicao()
    for termo in outra.termos:
        sql(
            "INSERT INTO aceites_termos(termo_id,usuario_id) VALUES(:t,:u)", t=termo, u=mentor["id"]
        )
    assert atribuir(client, s, mentor).status_code == 201
    assert atribuir(client, s, mentor, outra.equipes[0]).status_code == 409


def test_reducao_abaixo_do_uso_recusada(client, s):
    mentor = s.mentor(cap=2)
    assert atribuir(client, s, mentor).status_code == 201
    assert atribuir(client, s, mentor, s.equipes[1]).status_code == 201
    assert (
        client.patch(
            f"/admin/mentores/{mentor['id']}",
            headers=headers(s.cientifico),
            json={"max_equipes": 1},
        ).status_code
        == 409
    )


def test_substituicao_preserva_historico_e_libera_vaga(client, s, sql):
    a, b = s.mentor(cap=1), s.mentor(cap=1)
    inicial = atribuir(client, s, a).json()
    troca = substituir(client, s, b, inicial)
    assert troca.status_code == 200, troca.text
    atual = troca.json()
    assert atual["atribuicao_anterior_id"] == inicial["id"]
    hist = client.get(url(s.equipes[0]) + "/historico", headers=headers(s.cientifico)).json()
    assert len(hist) == 2
    antigo = next(h for h in hist if h["id"] == inicial["id"])
    assert antigo["encerrada_em"] and antigo["encerrada_por"] == str(s.cientifico["id"])
    assert antigo["motivo_encerramento"] == "Substituição administrativa"
    assert atribuir(client, s, a, s.equipes[1]).status_code == 201
    assert substituir(client, s, a, inicial).status_code == 409
    assert substituir(client, s, b, atual).status_code == 409


def test_substituicao_falha_preserva_vinculo(client, s, sql):
    a, b = s.mentor(cap=1), s.mentor(cap=1)
    inicial = atribuir(client, s, a).json()
    assert atribuir(client, s, b, s.equipes[1]).status_code == 201
    assert substituir(client, s, b, inicial).status_code == 409
    assert (
        client.get(url(s.equipes[0]), headers=headers(s.cientifico)).json()["id"] == inicial["id"]
    )
    assert len(sql("SELECT 1 FROM atribuicoes_mentor WHERE equipe_id=:e", e=s.equipes[0])) == 1


def test_encerramento_e_reinicio_da_cadeia(client, s):
    mentor = s.mentor(cap=1)
    atual = atribuir(client, s, mentor).json()
    encerramento = {"atribuicao_atual_id": atual["id"], "motivo": "Fim do acompanhamento"}
    rota = url(s.equipes[0]) + "/encerrar"
    assert client.post(rota, headers=headers(s.cientifico), json=encerramento).status_code == 200
    assert client.post(rota, headers=headers(s.cientifico), json=encerramento).status_code == 409
    assert client.get(url(s.equipes[0]), headers=headers(s.cientifico)).status_code == 404
    novo = atribuir(client, s, mentor)
    assert novo.status_code == 201
    assert novo.json()["atribuicao_anterior_id"] == atual["id"]


def test_isolamento_das_equipes_e_dos_mentores(client, s):
    a, b = s.mentor(), s.mentor()
    membro, estranho = s.membro(), s.membro(s.equipes[1])
    assert atribuir(client, s, a).status_code == 201
    resposta = client.get(f"/equipes/{s.equipes[0]}/mentor", headers=headers(membro))
    assert resposta.status_code == 200
    assert resposta.json()["mentor"]["id"] == str(a["id"])
    assert set(resposta.json()["mentor"]) == {
        "id",
        "nome",
        "email",
        "empresa_parceira",
        "area_atuacao",
        "ativo",
    }
    for usuario in (estranho, a, b, s.cientifico):
        assert (
            client.get(f"/equipes/{s.equipes[0]}/mentor", headers=headers(usuario)).status_code
            == 403
        )
    assert len(client.get("/me/mentoria/equipes", headers=headers(a)).json()) == 1
    assert client.get("/me/mentoria/equipes", headers=headers(b)).json() == []
    assert client.get(f"/admin/mentores/{a['id']}/equipes", headers=headers(b)).status_code == 403


def test_listagem_filtros_e_mentor_desativado(client, s):
    mentor = s.mentor()
    membro = s.membro()
    assert atribuir(client, s, mentor).status_code == 201
    lista = f"/admin/mentores/{mentor['id']}/equipes"
    assert len(client.get(lista, headers=headers(s.cientifico)).json()) == 1
    assert (
        client.get(lista + f"?hackathon_id={uuid4()}", headers=headers(s.cientifico)).json() == []
    )
    assert client.get(lista + "?limite=0", headers=headers(s.cientifico)).status_code == 422
    assert (
        client.post(
            f"/admin/mentores/{mentor['id']}/desativar", headers=headers(s.cientifico)
        ).status_code
        == 200
    )
    assert atribuir(client, s, mentor, s.equipes[1]).status_code == 409
    assert not client.get(f"/equipes/{s.equipes[0]}/mentor", headers=headers(membro)).json()[
        "mentor"
    ]["ativo"]


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO"])
def test_permissoes_administrativas(client, s, usuario_no_banco, papel):
    usuario = usuario_no_banco(papel=papel, senha=None)
    cabecalho = headers(usuario)
    for metodo, sufixo, dados in [
        ("post", "", {"mentor_id": str(uuid4())}),
        (
            "put",
            "",
            {"mentor_id": str(uuid4()), "atribuicao_atual_id": str(uuid4()), "motivo": "Troca"},
        ),
        ("get", "", None),
        ("get", "/historico", None),
        ("post", "/encerrar", {"atribuicao_atual_id": str(uuid4()), "motivo": "Fim"}),
    ]:
        assert (
            client.request(
                metodo, url(s.equipes[0]) + sufixo, headers=cabecalho, json=dados
            ).status_code
            == 403
        )


def test_sem_token_e_gestor_pendente(client, s, usuario_no_banco):
    assert client.get(url(s.equipes[0])).status_code == 401
    pendente = usuario_no_banco(papel="COMITE_CIENTIFICO", situacao_conta="PENDENTE", senha=None)
    assert client.get(url(s.equipes[0]), headers=headers(pendente)).status_code == 403


@pytest.mark.parametrize("campo", ["mentor_id", "ativo", "hackathon_id", "atribuido_por"])
def test_validacao_e_mass_assignment(client, s, campo):
    dados = {"mentor_id": str(s.mentor()["id"])}
    if campo == "mentor_id":
        dados[campo] = "inválido"
    else:
        dados[campo] = str(uuid4())
    assert (
        client.post(url(s.equipes[0]), headers=headers(s.cientifico), json=dados).status_code == 422
    )


def test_treinamento_auditado_idempotente_e_permissoes(client, s, sql):
    sql(
        "UPDATE hackathon SET treinamento_concluido_em=NULL,"
        "treinamento_concluido_por=NULL WHERE id=:h",
        h=s.h,
    )
    rota = f"/admin/hackathons/{s.h}/treinamento"
    assert (
        client.get(rota, headers=headers(s.cientifico)).json()["treinamento_concluido_em"] is None
    )
    assert client.post(rota + "/concluir", headers=headers(s.cientifico)).status_code == 403
    primeira = client.post(rota + "/concluir", headers=headers(s.organizador))
    assert primeira.status_code == 200
    assert primeira.json()["treinamento_concluido_por"] == str(s.organizador["id"])
    assert client.post(rota + "/concluir", headers=headers(s.organizador)).json() == primeira.json()


def test_treinamento_exige_homologacao(client, s, sql):
    sql("DELETE FROM resultados_proposta WHERE hackathon_id=:h", h=s.h)
    sql("DELETE FROM homologacoes_resultado WHERE hackathon_id=:h", h=s.h)
    assert (
        client.post(
            f"/admin/hackathons/{s.h}/treinamento/concluir", headers=headers(s.organizador)
        ).status_code
        == 409
    )


def test_notifica_todos_atomicamente_e_entrega(client, s, sql, processar):
    mentor = s.mentor()
    membros = [s.membro(), s.membro()]
    resposta = atribuir(client, s, mentor)
    assert resposta.status_code == 201
    eventos = sql(
        "SELECT * FROM eventos_notificacao_mentoria WHERE atribuicao_id=:a",
        a=UUID(resposta.json()["id"]),
    )
    assert {e["usuario_id"] for e in eventos} == {mentor["id"], *(m["id"] for m in membros)}
    assert all(e["email_enfileirado"] and e["publicado_na_plataforma_em"] is None for e in eventos)
    provedor = ProvedorMemoria()
    assert processar(provedor).enviados == 3
    assert {m.destinatario for m in provedor.enviadas} == {
        mentor["email"],
        *(m["email"] for m in membros),
    }
    assert all("segredo123" not in m.texto for m in provedor.enviadas)
    assert atribuir(client, s, mentor).status_code == 409
    assert (
        len(
            sql(
                "SELECT 1 FROM eventos_notificacao_mentoria WHERE atribuicao_id=:a",
                a=UUID(resposta.json()["id"]),
            )
        )
        == 3
    )


def test_substituicao_notifica_anterior_novo_e_equipe(client, s, sql):
    a, b = s.mentor(), s.mentor()
    membro = s.membro()
    inicial = atribuir(client, s, a).json()
    nova = substituir(client, s, b, inicial).json()
    eventos = sql(
        "SELECT * FROM eventos_notificacao_mentoria WHERE atribuicao_id=:a", a=UUID(nova["id"])
    )
    assert {e["usuario_id"] for e in eventos} == {a["id"], b["id"], membro["id"]}
    assert {e["tipo"] for e in eventos} == {"SUBSTITUIDA"}


def test_falha_de_notificacao_desfaz_atribuicao(client, s, sql, monkeypatch):
    from app.services.atribuicao_mentor import notificar

    async def falhar(*args, **kwargs):
        await notificar(*args, **kwargs)
        raise HTTPException(409, "Falha simulada após os avisos")

    monkeypatch.setattr("app.services.atribuicao_mentor.notificar", falhar)
    assert atribuir(client, s, s.mentor()).status_code == 409
    assert sql("SELECT 1 FROM atribuicoes_mentor WHERE hackathon_id=:h", h=s.h) == []
    assert sql("SELECT 1 FROM emails_outbox WHERE tipo='ATRIBUICAO_MENTOR'") == []


def test_falha_enfileiramento_preserva_evento_e_atribuicao(client, s, sql, monkeypatch):
    async def falhar(*args, **kwargs):
        return False

    monkeypatch.setattr("app.services.notificacao_mentoria.enfileirar", falhar)
    resposta = atribuir(client, s, s.mentor())
    assert resposta.status_code == 201
    eventos = sql(
        "SELECT * FROM eventos_notificacao_mentoria WHERE atribuicao_id=:a",
        a=UUID(resposta.json()["id"]),
    )
    assert eventos and all(not e["email_enfileirado"] for e in eventos)


def test_concorrencia_mesma_equipe(client, s):
    mentores = [s.mentor(), s.mentor()]
    barreira = Barrier(2)

    def executar(mentor):
        barreira.wait(timeout=10)
        return atribuir(client, s, mentor).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(executar, mentores)) == [201, 409]


def test_concorrencia_ultima_vaga(client, s, sql):
    mentor = s.mentor(cap=1)
    barreira = Barrier(2)

    def executar(equipe):
        barreira.wait(timeout=10)
        return atribuir(client, s, mentor, equipe).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(executar, s.equipes[:2])) == [201, 409]
    assert (
        len(
            sql(
                "SELECT 1 FROM atribuicoes_mentor WHERE mentor_id=:m AND encerrada_em IS NULL",
                m=mentor["id"],
            )
        )
        == 1
    )


def test_substituicoes_simultaneas(client, s):
    inicial = atribuir(client, s, s.mentor()).json()
    mentores = [s.mentor(), s.mentor()]
    barreira = Barrier(2)

    def executar(mentor):
        barreira.wait(timeout=10)
        return substituir(client, s, mentor, inicial).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(executar, mentores)) == [200, 409]


def test_indice_postgres_barra_dois_vigentes(client, s):
    mentor = s.mentor()
    assert atribuir(client, s, mentor).status_code == 201

    async def duplicar(conn):
        await sql_transacional(
            conn,
            "INSERT INTO atribuicoes_mentor(id,equipe_id,hackathon_id,mentor_id,atribuido_por)"
            " VALUES(:id,:e,:h,:m,:u)",
            id=uuid4(),
            e=s.equipes[0],
            h=s.h,
            m=mentor["id"],
            u=s.cientifico["id"],
        )

    with pytest.raises(IntegrityError, match="uq_atribuicoes_mentor_equipe_vigente"):
        rodar(duplicar)


def test_fk_postgres_barra_edicao_incorreta(s):
    outra = s.edicao()
    mentor = s.mentor()

    async def inserir(conn):
        await sql_transacional(
            conn,
            "INSERT INTO atribuicoes_mentor(id,equipe_id,hackathon_id,mentor_id,atribuido_por)"
            " VALUES(:id,:e,:h,:m,:u)",
            id=uuid4(),
            e=s.equipes[0],
            h=outra.h,
            m=mentor["id"],
            u=s.cientifico["id"],
        )

    with pytest.raises(IntegrityError, match="fk_atribuicoes_equipe_edicao"):
        rodar(inserir)


def test_swagger(client):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    for caminho in (
        "/admin/equipes/{equipe_id}/mentoria",
        "/equipes/{equipe_id}/mentor",
        "/me/mentoria/equipes",
        "/admin/mentores/{mentor_id}/equipes",
    ):
        for operacao in paths[caminho].values():
            assert operacao["security"]
            assert {"401", "403", "404", "409", "422"} <= operacao["responses"].keys()
    schema = spec["components"]["schemas"]
    assert {"motivo", "atribuicao_atual_id"} <= set(schema["AtribuicaoSubstituir"]["required"])
    assert "senha_hash" not in schema["MentorContato"]["properties"]


def test_be_s5_10_ativacao_real_antes_da_atribuicao(client, s, sql, novo_email):
    from tests.test_mentores import token_do_email

    cadastro = client.post(
        "/admin/mentores",
        headers=headers(s.cientifico),
        json={
            "nome": "Mentor Real",
            "email": novo_email(),
            "empresa_parceira": "Parceira",
            "area_atuacao": "Dados",
            "max_equipes": 1,
            "hackathon_id": str(s.h),
        },
    )
    assert cadastro.status_code == 201
    mentor = cadastro.json()
    assert atribuir(client, s, {"id": mentor["id"]}).status_code == 409
    ativacao = client.post(
        "/mentores/ativacao",
        json={
            "token": token_do_email(sql, mentor),
            "hackathon_id": str(s.h),
            "nome": "Mentor Real",
            "empresa_parceira": "Parceira",
            "area_atuacao": "Dados",
            "senha": "Segredo123",
            "termos_ids": [str(t) for t in s.termos],
        },
    )
    assert ativacao.status_code == 200
    assert atribuir(client, s, {"id": mentor["id"]}).status_code == 201


def test_trocas_cruzadas_nao_causam_deadlock(client, s, sql):
    a, b = s.mentor(cap=2), s.mentor(cap=2)
    x = atribuir(client, s, a).json()
    y = atribuir(client, s, b, s.equipes[1]).json()
    barreira = Barrier(2)

    def trocar(mentor, atual, equipe):
        barreira.wait(timeout=10)
        return substituir(client, s, mentor, atual, equipe=equipe).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        primeira = pool.submit(trocar, b, x, s.equipes[0])
        segunda = pool.submit(trocar, a, y, s.equipes[1])
        assert primeira.result(timeout=30) == segunda.result(timeout=30) == 200
    assert len(sql("SELECT 1 FROM atribuicoes_mentor WHERE hackathon_id=:h", h=s.h)) == 4


def test_rollback_de_substituicao_preserva_anterior_e_avisos(client, s, sql, monkeypatch):
    from app.services.atribuicao_mentor import notificar

    a, b = s.mentor(), s.mentor()
    inicial = atribuir(client, s, a).json()

    async def falhar(*args, **kwargs):
        await notificar(*args, **kwargs)
        raise HTTPException(409, "Falha após notificar a troca")

    monkeypatch.setattr("app.services.atribuicao_mentor.notificar", falhar)
    assert substituir(client, s, b, inicial).status_code == 409
    assert (
        client.get(url(s.equipes[0]), headers=headers(s.cientifico)).json()["id"] == inicial["id"]
    )
    assert len(sql("SELECT 1 FROM atribuicoes_mentor WHERE hackathon_id=:h", h=s.h)) == 1
    assert sql("SELECT 1 FROM eventos_notificacao_mentoria WHERE tipo='SUBSTITUIDA'") == []


def test_eventos_pendentes_para_a_central_sem_publicacao_ficticia(client, s):
    from app.controllers.atribuicao_mentor import eventos_pendentes_plataforma
    from tests.test_email_fila import com_sessao

    membro = s.membro()
    assert atribuir(client, s, s.mentor()).status_code == 201
    # O endpoint atual é específico de resultado, não uma central genérica já implementada.
    assert client.get("/me/notificacoes", headers=headers(membro)).json() == []

    async def consumir(db):
        eventos = await eventos_pendentes_plataforma(db)
        assert len(eventos) == 2
        assert all(e.publicado_na_plataforma_em is None for e in eventos)
        from datetime import UTC, datetime

        eventos[0].publicado_na_plataforma_em = datetime.now(UTC)
        db.add(eventos[0])
        await db.commit()
        assert len(await eventos_pendentes_plataforma(db)) == 1

    com_sessao(consumir)
