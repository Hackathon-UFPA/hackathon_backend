"""BE-S6-03: feedbacks do mentor e histórico da mentoria (RF40, RF42, RN16, RN17)."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.const.config import settings
from tests.test_atribuicoes_mentor import headers, s, substituir
from tests.test_painel_mentor import acompanhar, calendario, detalhe, organizacao, painel

__all__ = ["s", "calendario", "organizacao"]  # fixtures reaproveitadas

TEXTO = "Priorizem o fluxo de cadastro antes do próximo marco."


@pytest.fixture(autouse=True)
def _limpeza(s, calendario, fila_vazia):
    """Depende de `s` e `calendario` para rodar antes da limpeza deles: feedbacks apontam para
    equipes, marcos e entregas. O trigger de imutabilidade é contornado só aqui, na sessão de
    limpeza, com `session_replication_role` (o banco de testes usa um superusuário)."""
    yield

    async def apagar():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SET LOCAL session_replication_role = replica"))
                await conn.execute(
                    text(
                        "DELETE FROM feedbacks_mentoria WHERE hackathon_id IN"
                        " (SELECT id FROM hackathon WHERE nome = 'Mentoria')"
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(apagar())


def rota(equipe, final="feedbacks"):
    return f"/equipes/{equipe}/mentoria/{final}"


def escrever(client, usuario, equipe, texto=TEXTO, status="NO_RITMO", chave=None, **extras):
    cabecalhos = headers(usuario) | ({"Idempotency-Key": chave} if chave else {})
    return client.post(
        rota(equipe),
        headers=cabecalhos,
        json={"texto": texto, "status_acompanhamento": status, **extras},
    )


def ler(client, usuario, equipe, final="feedbacks", **params):
    return client.get(rota(equipe, final), headers=headers(usuario), params=params)


@pytest.fixture
def cenario(client, s):
    """Equipe 0 com mentor vigente e um integrante, todos prontos para o fluxo."""
    mentor = s.mentor()
    atribuicao = acompanhar(client, s, mentor, s.equipes[0])
    integrante = s.membro(s.equipes[0])
    return type("C", (), {"mentor": mentor, "integrante": integrante, "atribuicao": atribuicao})


def criar(client, cenario, s, **extras):
    resposta = escrever(client, cenario.mentor, s.equipes[0], **extras)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


# ---------- escrita e permissões ----------


def test_mentor_registra_feedback(client, s, cenario):
    corpo = criar(client, cenario, s, status="ATENCAO")
    assert corpo["texto"] == TEXTO
    assert corpo["status_acompanhamento"] == "ATENCAO"
    assert corpo["equipe_id"] == str(s.equipes[0])
    assert corpo["marco_id"] is None and corpo["entrega_id"] is None
    assert corpo["autor_nome"] == "Mentor Completo"
    assert corpo["corrige_id"] is None and corpo["corrigido_por_id"] is None
    assert "atribuicao_id" not in corpo and "autor_id" not in corpo


def test_autor_vem_do_jwt_e_campos_extras_sao_recusados(client, s, cenario, sql):
    resposta = escrever(client, cenario.mentor, s.equipes[0], autor_id=str(uuid4()))
    assert resposta.status_code == 422
    corpo = criar(client, cenario, s)
    linha = sql(
        "SELECT autor_id, atribuicao_id FROM feedbacks_mentoria WHERE id=:i", i=corpo["id"]
    )[0]
    assert linha["autor_id"] == cenario.mentor["id"]
    assert str(linha["atribuicao_id"]) == cenario.atribuicao["id"]


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "COMITE_TECNICO", "COMITE_CIENTIFICO"])
def test_outros_perfis_nao_escrevem(client, s, cenario, usuario_no_banco, papel):
    usuario = usuario_no_banco(papel=papel, senha=None)
    assert escrever(client, usuario, s.equipes[0]).status_code == 403


def test_integrante_e_gestor_nao_escrevem(client, s, cenario):
    assert escrever(client, cenario.integrante, s.equipes[0]).status_code == 403
    assert escrever(client, s.cientifico, s.equipes[0]).status_code == 403
    assert escrever(client, s.organizador, s.equipes[0]).status_code == 403


def test_dev_escreve_com_atribuicao_vigente(client, s, cenario, usuario_no_banco):
    dev = usuario_no_banco(papel="DEV", senha=None)
    assert escrever(client, dev, s.equipes[0]).status_code == 201
    # Sem mentor vigente não há vínculo para registrar.
    assert escrever(client, dev, s.equipes[1]).status_code == 409


def test_escrita_sem_autenticacao(client, s):
    resposta = client.post(
        rota(s.equipes[0]), json={"texto": "x", "status_acompanhamento": "NO_RITMO"}
    )
    assert resposta.status_code == 401


def test_404_igual_para_equipe_inexistente_e_de_outro_mentor(client, s, cenario):
    outro = s.mentor()
    acompanhar(client, s, outro, s.equipes[1])
    de_outro = escrever(client, outro, s.equipes[0])
    inexistente = escrever(client, outro, uuid4())
    assert de_outro.status_code == inexistente.status_code == 404
    assert de_outro.json() == inexistente.json()
    # Equipe sem nenhuma atribuição também não aparece para um mentor.
    assert escrever(client, outro, s.equipes[2]).status_code == 404


@pytest.mark.parametrize(
    "corpo",
    [
        {"texto": "", "status_acompanhamento": "NO_RITMO"},
        {"texto": "   ", "status_acompanhamento": "NO_RITMO"},
        {"texto": "x" * 5001, "status_acompanhamento": "NO_RITMO"},
        {"texto": "ok", "status_acompanhamento": "OUTRO"},
        {"texto": "ok"},
        {"status_acompanhamento": "NO_RITMO"},
        {"texto": "ok", "status_acompanhamento": "NO_RITMO", "marco_id": "abc"},
    ],
)
def test_payload_invalido(client, s, cenario, corpo):
    resposta = client.post(rota(s.equipes[0]), headers=headers(cenario.mentor), json=corpo)
    assert resposta.status_code == 422


def test_texto_no_limite_e_aparado(client, s, cenario):
    assert criar(client, cenario, s, texto="x" * 5000)["texto"] == "x" * 5000
    assert criar(client, cenario, s, texto="  com bordas  ")["texto"] == "com bordas"


@pytest.mark.parametrize("status", ["NO_RITMO", "ATENCAO", "EM_RISCO", "CONCLUIDO"])
def test_todos_os_status(client, s, cenario, status):
    assert criar(client, cenario, s, status=status)["status_acompanhamento"] == status


def test_edicao_encerrada_bloqueia_escrita_e_mantem_leitura(client, s, cenario, sql):
    existente = criar(client, cenario, s)
    for status in ("FINALIZADO", "CANCELADO"):
        sql("UPDATE hackathon SET status=CAST(:s AS status_hackathon) WHERE id=:h", s=status, h=s.h)
        assert escrever(client, cenario.mentor, s.equipes[0]).status_code == 409
        corrigir = escrever(client, cenario.mentor, s.equipes[0], corrige_id=existente["id"])
        assert corrigir.status_code == 409
        for quem in (cenario.mentor, cenario.integrante, s.cientifico):
            resposta = ler(client, quem, s.equipes[0])
            assert resposta.status_code == 200
            assert [f["id"] for f in resposta.json()] == [existente["id"]]
            assert ler(client, quem, s.equipes[0], "historico").status_code == 200


def test_equipe_inelegivel(client, s, cenario, sql):
    sql("UPDATE equipes SET situacao='NAO_HOMOLOGADA' WHERE id=:e", e=s.equipes[0])
    assert escrever(client, cenario.mentor, s.equipes[0]).status_code == 409


def test_equipe_sem_proposta_aprovada(client, s, cenario, sql):
    # A API não atribui equipe reprovada, e o resultado homologado é imutável: o vínculo vai
    # direto ao banco para simular a equipe que deixou de ser elegível.
    sql(
        "INSERT INTO atribuicoes_mentor(id,equipe_id,hackathon_id,mentor_id,atribuido_por)"
        " VALUES(:i,:e,:h,:m,:u)",
        i=uuid4(),
        e=s.equipes[2],
        h=s.h,
        m=cenario.mentor["id"],
        u=s.cientifico["id"],
    )
    assert escrever(client, cenario.mentor, s.equipes[2]).status_code == 409


# ---------- vínculos com marco e entrega ----------


def test_feedback_com_marco_e_com_entrega(client, s, cenario, calendario):
    marco = calendario.marco("Protótipo", 5)
    outro_marco = calendario.marco("Outro", 6)
    calendario.entrega(marco, s.equipes[0], cenario.integrante["id"])
    entrega = ler(client, cenario.integrante, s.equipes[0], "historico").json()[0]["entrega"]

    so_marco = criar(client, cenario, s, marco_id=str(marco))
    assert so_marco["marco_id"] == str(marco) and so_marco["entrega_id"] is None
    so_entrega = criar(client, cenario, s, entrega_id=entrega["id"])
    assert so_entrega["marco_id"] == str(marco)  # derivado da entrega
    os_dois = criar(client, cenario, s, entrega_id=entrega["id"], marco_id=str(marco))
    assert os_dois["entrega_id"] == entrega["id"]

    divergente = escrever(
        client, cenario.mentor, s.equipes[0], entrega_id=entrega["id"], marco_id=str(outro_marco)
    )
    assert divergente.status_code == 422


def test_vinculos_inconsistentes(client, s, cenario, calendario, sql):
    # Entrega de outra equipe da mesma edição.
    marco = calendario.marco("Protótipo", 5)
    calendario.entrega(marco, s.equipes[1], s.membro(s.equipes[1])["id"])
    entrega_alheia = sql("SELECT id FROM entregas_mentoria WHERE equipe_id=:e", e=s.equipes[1])[0]
    resposta = escrever(client, cenario.mentor, s.equipes[0], entrega_id=str(entrega_alheia["id"]))
    assert resposta.status_code == 422
    # Marco de outra edição e marco/entrega inexistentes.
    outra = s.edicao()
    marco_de_outra = calendario.marco("Outra edição", 5, hackathon_id=outra.h)
    for extras in (
        {"marco_id": str(marco_de_outra)},
        {"marco_id": str(uuid4())},
        {"entrega_id": str(uuid4())},
    ):
        assert escrever(client, cenario.mentor, s.equipes[0], **extras).status_code == 422


def test_banco_recusa_vinculos_inconsistentes(client, s, cenario, calendario, sql):
    marco = calendario.marco("Protótipo", 5)
    outro_marco = calendario.marco("Outro", 6)
    calendario.entrega(marco, s.equipes[0], cenario.integrante["id"])
    entrega = sql("SELECT id FROM entregas_mentoria WHERE equipe_id=:e", e=s.equipes[0])[0]["id"]
    insercao = (
        "INSERT INTO feedbacks_mentoria(id,equipe_id,hackathon_id,atribuicao_id,autor_id,"
        "marco_id,entrega_id,status_acompanhamento,texto) VALUES(:i,:e,:h,:a,:u,:m,:en,"
        "'NO_RITMO','x')"
    )
    base = dict(e=s.equipes[0], h=s.h, a=cenario.atribuicao["id"], u=cenario.mentor["id"])
    for extras in (
        {"m": outro_marco, "en": entrega},  # marco diverge da entrega
        {"m": None, "en": entrega},  # entrega sem marco escaparia da FK composta
    ):
        with pytest.raises(Exception, match="feedbacks_mentoria"):
            sql(insercao, i=uuid4(), **base, **extras)


# ---------- imutabilidade e correção ----------


def test_trigger_bloqueia_update_e_delete(client, s, cenario, sql):
    feedback = criar(client, cenario, s)
    with pytest.raises(Exception, match="imutável"):
        sql("UPDATE feedbacks_mentoria SET texto='alterado' WHERE id=:i", i=feedback["id"])
    with pytest.raises(Exception, match="imutável"):
        sql("DELETE FROM feedbacks_mentoria WHERE id=:i", i=feedback["id"])
    assert (
        sql("SELECT texto FROM feedbacks_mentoria WHERE id=:i", i=feedback["id"])[0]["texto"]
        == TEXTO
    )


def test_apagar_equipe_ou_usuario_com_feedback_e_recusado(client, s, cenario, sql):
    criar(client, cenario, s)
    with pytest.raises(Exception, match="foreign key"):
        sql("DELETE FROM equipes WHERE id=:e", e=s.equipes[0])
    with pytest.raises(Exception, match="foreign key"):
        sql("DELETE FROM usuarios WHERE id=:u", u=cenario.mentor["id"])


def test_correcao_cria_nova_linha_e_marca_o_original(client, s, cenario, sql):
    original = criar(client, cenario, s, texto="Versão com erro", status="EM_RISCO")
    nova = criar(client, cenario, s, texto="Versão certa", corrige_id=original["id"])
    assert nova["corrige_id"] == original["id"]
    assert (
        sql("SELECT count(*) AS n FROM feedbacks_mentoria WHERE equipe_id=:e", e=s.equipes[0])[0][
            "n"
        ]
        == 2
    )
    lista = ler(client, cenario.integrante, s.equipes[0]).json()
    por_id = {f["id"]: f for f in lista}
    assert por_id[original["id"]]["corrigido_por_id"] == nova["id"]
    assert por_id[original["id"]]["texto"] == "Versão com erro"  # o original nunca muda
    assert por_id[nova["id"]]["corrigido_por_id"] is None


def test_segunda_correcao_do_mesmo_feedback_da_409(client, s, cenario):
    original = criar(client, cenario, s)
    criar(client, cenario, s, corrige_id=original["id"])
    segunda = escrever(client, cenario.mentor, s.equipes[0], corrige_id=original["id"])
    assert segunda.status_code == 409


def test_correcoes_simultaneas_so_uma_vence(client, s, cenario, sql):
    original = criar(client, cenario, s)
    barreira = Barrier(2)

    def corrigir(n):
        barreira.wait(timeout=10)
        return escrever(
            client, cenario.mentor, s.equipes[0], texto=f"Correção {n}", corrige_id=original["id"]
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(corrigir, [1, 2])) == [201, 409]
    assert (
        sql("SELECT count(*) AS n FROM feedbacks_mentoria WHERE corrige_id=:i", i=original["id"])[
            0
        ]["n"]
        == 1
    )


def test_correcao_de_outro_autor_ou_de_outra_equipe(client, s, cenario):
    original = criar(client, cenario, s)
    # O mentor novo lê o histórico, mas não corrige o feedback do anterior: escreve um novo.
    novo = s.mentor()
    assert substituir(client, s, novo, cenario.atribuicao).status_code == 200
    resposta = escrever(client, novo, s.equipes[0], corrige_id=original["id"])
    assert resposta.status_code == 422
    # Feedback de outra equipe tem a mesma resposta de um feedback inexistente.
    outro = s.mentor()
    acompanhar(client, s, outro, s.equipes[1])
    de_outra = escrever(client, outro, s.equipes[1], corrige_id=original["id"])
    inexistente = escrever(client, outro, s.equipes[1], corrige_id=str(uuid4()))
    assert de_outra.status_code == inexistente.status_code == 422
    assert de_outra.json() == inexistente.json()


def test_banco_recusa_correcao_de_outra_equipe(client, s, cenario, sql):
    original = criar(client, cenario, s)
    with pytest.raises(Exception, match="fk_feedbacks_mentoria_corrige"):
        sql(
            "INSERT INTO feedbacks_mentoria(id,equipe_id,hackathon_id,atribuicao_id,autor_id,"
            "status_acompanhamento,texto,corrige_id) VALUES(:i,:e,:h,:a,:u,'NO_RITMO','x',:c)",
            i=uuid4(),
            e=s.equipes[1],
            h=s.h,
            a=cenario.atribuicao["id"],
            u=cenario.mentor["id"],
            c=original["id"],
        )


# ---------- leitura ----------


def test_leitura_por_perfil(client, s, cenario, usuario_no_banco):
    criar(client, cenario, s)
    permitidos = [
        cenario.mentor,
        cenario.integrante,
        s.cientifico,
        s.organizador,
        usuario_no_banco(papel="DEV", senha=None),
    ]
    for quem in permitidos:
        for final in ("feedbacks", "historico"):
            resposta = ler(client, quem, s.equipes[0], final)
            assert resposta.status_code == 200, (quem, final)
            assert len(resposta.json()) == 1
    negados = [
        s.mentor(),
        usuario_no_banco(senha=None),  # participante de fora da equipe
        usuario_no_banco(papel="COMITE_TECNICO", senha=None),  # avaliador
        s.membro(s.equipes[1]),  # integrante de outra equipe
    ]
    inexistente = ler(client, negados[0], uuid4())
    for quem in negados:
        for final in ("feedbacks", "historico"):
            resposta = ler(client, quem, s.equipes[0], final)
            assert resposta.status_code == 404, (quem, final)
            assert resposta.json() == inexistente.json()


def test_leitura_sem_autenticacao(client, s):
    assert client.get(rota(s.equipes[0])).status_code == 401


def test_mentor_substituido_perde_acesso_e_o_novo_ve_o_historico(client, s, cenario):
    antigo_feedback = criar(client, cenario, s)
    novo = s.mentor()
    assert substituir(client, s, novo, cenario.atribuicao).status_code == 200

    for final in ("feedbacks", "historico"):
        assert ler(client, cenario.mentor, s.equipes[0], final).status_code == 404
    assert escrever(client, cenario.mentor, s.equipes[0]).status_code == 404

    lista = ler(client, novo, s.equipes[0]).json()
    assert [f["id"] for f in lista] == [antigo_feedback["id"]]
    assert lista[0]["autor_nome"] == "Mentor Completo"
    assert "autor_id" not in lista[0] and "atribuicao_id" not in lista[0]
    escrito = escrever(client, novo, s.equipes[0], texto="Meu feedback")
    assert escrito.status_code == 201
    assert escrito.json()["corrige_id"] is None
    # O vínculo registrado no banco é o do mentor novo.


def test_vinculo_encerrado_perde_acesso(client, s, cenario):
    resposta = client.post(
        f"/admin/equipes/{s.equipes[0]}/mentoria/encerrar",
        headers=headers(s.cientifico),
        json={"atribuicao_atual_id": cenario.atribuicao["id"], "motivo": "Fim"},
    )
    if resposta.status_code == 404:
        pytest.skip("rota de encerramento não existe com este caminho")
    assert ler(client, cenario.mentor, s.equipes[0]).status_code == 404


def test_duas_organizacoes(client, s, cenario, organizacao, sql, usuario_no_banco):
    criar(client, cenario, s)
    org_a, org_b = organizacao(), organizacao()
    sql("UPDATE hackathon SET organizacao_id=:o WHERE id=:h", o=org_a, h=s.h)
    sql(
        "UPDATE usuarios SET organizacao_id=:o WHERE id=ANY(:ids)",
        o=org_a,
        ids=[cenario.mentor["id"], s.cientifico["id"], s.organizador["id"]],
    )
    gestor_b = usuario_no_banco(papel="ORGANIZADOR", senha=None)
    sql("UPDATE usuarios SET organizacao_id=:o WHERE id=:u", o=org_b, u=gestor_b["id"])
    mentor_b = s.mentor()
    sql("UPDATE usuarios SET organizacao_id=:o WHERE id=:u", o=org_b, u=mentor_b["id"])

    assert ler(client, s.organizador, s.equipes[0]).status_code == 200
    assert ler(client, gestor_b, s.equipes[0]).status_code == 404
    assert ler(client, gestor_b, s.equipes[0], "historico").status_code == 404
    assert ler(client, mentor_b, s.equipes[0]).status_code == 404
    assert escrever(client, mentor_b, s.equipes[0]).status_code == 404
    assert escrever(client, cenario.mentor, s.equipes[0]).status_code == 201
    # Mentor da organização dona da edição que perde o vínculo com a organização também sai.
    sql("UPDATE usuarios SET organizacao_id=:o WHERE id=:u", o=org_b, u=cenario.mentor["id"])
    assert ler(client, cenario.mentor, s.equipes[0]).status_code == 404
    assert escrever(client, cenario.mentor, s.equipes[0]).status_code == 404


def test_paginacao_e_ordem_estavel_com_empate(client, s, cenario, sql):
    ids = [criar(client, cenario, s, texto=f"Feedback {n}")["id"] for n in range(5)]
    # Tudo no mesmo instante: o desempate é o id.
    sql("ALTER TABLE feedbacks_mentoria DISABLE TRIGGER tg_feedbacks_mentoria_imutavel")
    try:
        sql(
            "UPDATE feedbacks_mentoria SET criado_em='2026-01-01T00:00:00Z' WHERE equipe_id=:e",
            e=s.equipes[0],
        )
    finally:
        sql("ALTER TABLE feedbacks_mentoria ENABLE TRIGGER tg_feedbacks_mentoria_imutavel")
    esperado = sorted(ids)
    completo = [f["id"] for f in ler(client, cenario.mentor, s.equipes[0]).json()]
    assert completo == esperado
    paginas = [
        [
            f["id"]
            for f in ler(client, cenario.mentor, s.equipes[0], limite=2, deslocamento=n).json()
        ]
        for n in (0, 2, 4, 6)
    ]
    assert paginas == [esperado[0:2], esperado[2:4], esperado[4:5], []]


def test_ordem_decrescente_por_data(client, s, cenario):
    primeiro = criar(client, cenario, s, texto="Primeiro")
    segundo = criar(client, cenario, s, texto="Segundo")
    lista = ler(client, cenario.integrante, s.equipes[0]).json()
    assert [f["id"] for f in lista] == [segundo["id"], primeiro["id"]]


@pytest.mark.parametrize("final", ["feedbacks", "historico"])
@pytest.mark.parametrize("params", [{"limite": 0}, {"limite": 101}, {"deslocamento": -1}])
def test_paginacao_invalida(client, s, cenario, final, params):
    assert ler(client, cenario.mentor, s.equipes[0], final, **params).status_code == 422


def test_limites_validos(client, s, cenario):
    criar(client, cenario, s)
    for params in ({"limite": 1}, {"limite": 100}, {"deslocamento": 0}):
        assert len(ler(client, cenario.mentor, s.equipes[0], **params).json()) == 1


# ---------- idempotência ----------


def test_sem_chave_cada_pedido_cria_um_feedback(client, s, cenario):
    primeiro, segundo = criar(client, cenario, s), criar(client, cenario, s)
    assert primeiro["id"] != segundo["id"]


def test_mesma_chave_e_mesmo_conteudo_devolve_o_mesmo(client, s, cenario, sql):
    primeira = escrever(client, cenario.mentor, s.equipes[0], chave="chave-1")
    repetida = escrever(client, cenario.mentor, s.equipes[0], chave="chave-1")
    assert (primeira.status_code, repetida.status_code) == (201, 200)
    assert primeira.json() == repetida.json()
    assert (
        sql("SELECT count(*) AS n FROM feedbacks_mentoria WHERE equipe_id=:e", e=s.equipes[0])[0][
            "n"
        ]
        == 1
    )


def test_mesma_chave_com_conteudo_diferente_da_409(client, s, cenario):
    escrever(client, cenario.mentor, s.equipes[0], chave="chave-2")
    for extras in ({"texto": "Outro texto"}, {"status": "EM_RISCO"}):
        assert (
            escrever(client, cenario.mentor, s.equipes[0], chave="chave-2", **extras).status_code
            == 409
        )


def test_chaves_diferentes_criam_dois(client, s, cenario):
    a = escrever(client, cenario.mentor, s.equipes[0], chave="a")
    b = escrever(client, cenario.mentor, s.equipes[0], chave="b")
    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["id"] != b.json()["id"]


def test_chave_com_entrega_derivada_repete_com_200(client, s, cenario, calendario):
    marco = calendario.marco("Protótipo", 5)
    calendario.entrega(marco, s.equipes[0], cenario.integrante["id"])
    entrega = ler(client, cenario.integrante, s.equipes[0], "historico").json()[0]["entrega"]
    primeira = escrever(client, cenario.mentor, s.equipes[0], chave="k", entrega_id=entrega["id"])
    repetida = escrever(client, cenario.mentor, s.equipes[0], chave="k", entrega_id=entrega["id"])
    assert (primeira.status_code, repetida.status_code) == (201, 200)


def test_chave_invalida(client, s, cenario):
    assert escrever(client, cenario.mentor, s.equipes[0], chave="x" * 129).status_code == 422


def test_chaves_iguais_de_autores_diferentes_nao_colidem(client, s, cenario):
    outro = s.mentor()
    acompanhar(client, s, outro, s.equipes[1])
    a = escrever(client, cenario.mentor, s.equipes[0], chave="mesma")
    b = escrever(client, outro, s.equipes[1], chave="mesma")
    assert (a.status_code, b.status_code) == (201, 201)


def test_pedidos_simultaneos_com_a_mesma_chave(client, s, cenario, sql):
    barreira = Barrier(2)

    def enviar(_):
        barreira.wait(timeout=10)
        return escrever(client, cenario.mentor, s.equipes[0], chave="corrida").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(enviar, [1, 2])) == [200, 201]
    assert (
        sql("SELECT count(*) AS n FROM feedbacks_mentoria WHERE equipe_id=:e", e=s.equipes[0])[0][
            "n"
        ]
        == 1
    )


# ---------- notificação ----------


def notificacoes(sql, feedback_id):
    return sql(
        "SELECT usuario_id, tipo, dados, referencia_tipo, referencia_id, mensagem, titulo"
        " FROM notificacoes WHERE chave_idempotencia=:c",
        c=f"feedback_mentoria:{feedback_id}",
    )


def test_integrantes_confirmados_recebem_uma_notificacao_sem_o_texto(
    client, s, cenario, sql, usuario_no_banco
):
    segundo = s.membro(s.equipes[0])
    de_fora = usuario_no_banco(senha=None)  # participante que não integra a equipe
    # Convite pendente não é integrante confirmado e não recebe o aviso.
    sql(
        "INSERT INTO convites(equipe_id,nome,email,usuario_id,convidado_por,status)"
        " VALUES(:e,'Convidado',:m,:u,:c,'PENDENTE')",
        e=s.equipes[0],
        m=de_fora["email"],
        u=de_fora["id"],
        c=cenario.integrante["id"],
    )
    try:
        feedback = criar(
            client, cenario, s, status="EM_RISCO", texto="Texto confidencial da mentoria"
        )
    finally:
        sql("DELETE FROM convites WHERE equipe_id=:e", e=s.equipes[0])

    linhas = notificacoes(sql, feedback["id"])
    assert {n["usuario_id"] for n in linhas} == {cenario.integrante["id"], segundo["id"]}
    assert de_fora["id"] not in {n["usuario_id"] for n in linhas}
    assert cenario.mentor["id"] not in {n["usuario_id"] for n in linhas}  # o autor não se avisa
    for linha in linhas:
        assert linha["tipo"] == "MENTOR"
        assert linha["referencia_tipo"] == "FEEDBACK_MENTORIA"
        assert str(linha["referencia_id"]) == feedback["id"]
        assert linha["dados"] == {
            "equipe_id": str(s.equipes[0]),
            "status_acompanhamento": "EM_RISCO",
        }
        assert "confidencial" not in str(linha).lower()


def test_repeticao_da_chave_nao_duplica_a_notificacao(client, s, cenario, sql):
    primeira = escrever(client, cenario.mentor, s.equipes[0], chave="notif").json()
    escrever(client, cenario.mentor, s.equipes[0], chave="notif")
    assert len(notificacoes(sql, primeira["id"])) == 1


def test_falha_ao_notificar_nao_derruba_o_feedback(client, s, cenario, sql, monkeypatch):
    async def falha(*_args, **_kwargs):
        raise RuntimeError("central indisponível")

    monkeypatch.setattr("app.services.notificacao.inserir_ignorando_repetidas", falha)
    resposta = escrever(client, cenario.mentor, s.equipes[0])
    assert resposta.status_code == 201
    assert notificacoes(sql, resposta.json()["id"]) == []
    assert len(ler(client, cenario.mentor, s.equipes[0]).json()) == 1


def test_nenhum_email_e_enfileirado(client, s, cenario, sql):
    antes = sql("SELECT count(*) AS n FROM emails_outbox")[0]["n"]  # e-mail da atribuição
    criar(client, cenario, s)
    assert sql("SELECT count(*) AS n FROM emails_outbox")[0]["n"] == antes


def test_equipe_sem_outros_integrantes_nao_notifica(client, s, cenario, sql):
    outro = s.mentor()
    acompanhar(client, s, outro, s.equipes[1])
    resposta = escrever(client, outro, s.equipes[1])
    assert resposta.status_code == 201
    assert notificacoes(sql, resposta.json()["id"]) == []


# ---------- painel ----------


def test_painel_traz_campos_novos_e_mantem_os_antigos(client, s, cenario, calendario):
    outro = cenario.mentor
    acompanhar(client, s, outro, s.equipes[1])
    marco = calendario.marco("Protótipo", 5)
    sem_feedback = painel(client, outro)
    antes = {e["equipe_id"]: e for e in sem_feedback["equipes"]}
    assert all(
        e["ultimo_feedback"] is None and e["dias_sem_feedback"] is None for e in antes.values()
    )
    assert sem_feedback["resumo"]["equipes_sem_feedback"] == 2

    fb = criar(client, cenario, s, status="ATENCAO", marco_id=str(marco))
    depois = painel(client, outro)
    por_equipe = {e["equipe_id"]: e for e in depois["equipes"]}
    com, sem = por_equipe[str(s.equipes[0])], por_equipe[str(s.equipes[1])]
    assert com["ultimo_feedback"]["id"] == fb["id"]
    assert com["ultimo_feedback"]["status_acompanhamento"] == "ATENCAO"
    assert set(com["ultimo_feedback"]) == {"id", "criado_em", "status_acompanhamento"}
    assert com["dias_sem_feedback"] == 0
    assert sem["ultimo_feedback"] is None and sem["dias_sem_feedback"] is None
    assert depois["resumo"]["equipes_sem_feedback"] == 1
    # Campos antigos idênticos.
    for chave, valor in antes[str(s.equipes[0])].items():
        if chave not in ("ultimo_feedback", "dias_sem_feedback"):
            assert com[chave] == valor


def test_painel_detalhe_com_feedbacks_recentes_sem_texto_completo(client, s, cenario):
    for n in range(7):
        criar(client, cenario, s, texto=f"{n} " + "z" * 300)
    corpo = detalhe(client, cenario.mentor, s.equipes[0]).json()
    recentes = corpo["feedbacks_recentes"]
    assert len(recentes) == 5
    assert recentes[0]["trecho"].startswith("6 ")
    assert all(len(f["trecho"]) <= 140 and "texto" not in f for f in recentes)
    assert recentes[0]["autor_nome"] == "Mentor Completo"
    assert corpo["ultimo_feedback"]["id"] == recentes[0]["id"]


def test_dias_sem_feedback_conta_dias_inteiros(client, s, cenario, sql):
    criar(client, cenario, s)
    sql("ALTER TABLE feedbacks_mentoria DISABLE TRIGGER tg_feedbacks_mentoria_imutavel")
    try:
        sql(
            "UPDATE feedbacks_mentoria SET criado_em = now() - interval '3 days 2 hours'"
            " WHERE equipe_id=:e",
            e=s.equipes[0],
        )
    finally:
        sql("ALTER TABLE feedbacks_mentoria ENABLE TRIGGER tg_feedbacks_mentoria_imutavel")
    assert painel(client, cenario.mentor)["equipes"][0]["dias_sem_feedback"] == 3


def test_painel_conta_feedback_de_mentor_anterior(client, s, cenario):
    criar(client, cenario, s)
    novo = s.mentor()
    assert substituir(client, s, novo, cenario.atribuicao).status_code == 200
    equipe = painel(client, novo)["equipes"][0]
    assert equipe["ultimo_feedback"] is not None and equipe["dias_sem_feedback"] == 0


# ---------- histórico ----------


def test_historico_junta_entregas_e_feedbacks_na_ordem(client, s, cenario, calendario, sql):
    antiga = calendario.marco("Antiga", -10)
    recente = calendario.marco("Recente", -5)
    calendario.entrega(antiga, s.equipes[0], cenario.integrante["id"])
    calendario.entrega(recente, s.equipes[0], cenario.integrante["id"])
    # Entregas em D-11 e D-6 (um dia antes dos prazos). O feedback é o mais novo.
    feedback = criar(client, cenario, s)

    itens = ler(client, cenario.integrante, s.equipes[0], "historico").json()
    assert [i["tipo"] for i in itens] == ["FEEDBACK", "ENTREGA", "ENTREGA"]
    assert itens[0]["feedback"]["id"] == feedback["id"] and "entrega" not in itens[0]
    assert itens[1]["entrega"]["marco_id"] == str(recente)
    assert itens[2]["entrega"]["marco_id"] == str(antiga)
    assert set(itens[1]["entrega"]) == {
        "id",
        "marco_id",
        "equipe_id",
        "hackathon_id",
        "enviado_por",
        "enviado_em",
        "data_limite_no_envio",
        "descricao",
        "referencias",
    }
    assert itens[1]["ocorrido_em"] == itens[1]["entrega"]["enviado_em"]
    assert itens[0]["ocorrido_em"] == itens[0]["feedback"]["criado_em"]
    # A entrega vem entre dois feedbacks quando as datas se intercalam.
    sql("ALTER TABLE feedbacks_mentoria DISABLE TRIGGER tg_feedbacks_mentoria_imutavel")
    try:
        sql(
            "UPDATE feedbacks_mentoria SET criado_em = now() - interval '8 days' WHERE id=:i",
            i=feedback["id"],
        )
    finally:
        sql("ALTER TABLE feedbacks_mentoria ENABLE TRIGGER tg_feedbacks_mentoria_imutavel")
    ordem = [i["tipo"] for i in ler(client, cenario.integrante, s.equipes[0], "historico").json()]
    assert ordem == ["ENTREGA", "FEEDBACK", "ENTREGA"]


def test_historico_paginado_sem_repetir_nem_perder(client, s, cenario, calendario):
    for n in range(3):
        calendario.entrega(
            calendario.marco(f"M{n}", -20 + n), s.equipes[0], cenario.integrante["id"]
        )
        criar(client, cenario, s, texto=f"F{n}")
    completo = ler(client, cenario.mentor, s.equipes[0], "historico").json()
    assert len(completo) == 6
    paginas = []
    for deslocamento in (0, 2, 4, 6):
        paginas += ler(
            client, cenario.mentor, s.equipes[0], "historico", limite=2, deslocamento=deslocamento
        ).json()
    assert paginas == completo


def test_historico_so_com_feedbacks_com_entregas_e_vazio(client, s, cenario, calendario):
    assert ler(client, cenario.mentor, s.equipes[0], "historico").json() == []
    criar(client, cenario, s)
    assert [i["tipo"] for i in ler(client, cenario.mentor, s.equipes[0], "historico").json()] == [
        "FEEDBACK"
    ]
    calendario.entrega(calendario.marco("M", 5), s.equipes[1], s.membro(s.equipes[1])["id"])
    # Entrega de outra equipe não entra.
    assert len(ler(client, cenario.mentor, s.equipes[0], "historico").json()) == 1


def test_historico_ignora_a_submissao_final(client, s, cenario, calendario, sql):
    final = calendario.marco("Final", 30, tipo="FINAL")
    calendario.entrega(final, s.equipes[0], cenario.integrante["id"])
    entrega = sql("SELECT id FROM entregas_mentoria WHERE marco_id=:m", m=final)[0]["id"]
    proposta = sql("SELECT id FROM submissoes WHERE equipe_id=:e", e=s.equipes[0])[0]["id"]
    sql(
        "INSERT INTO submissoes_finais(entrega_id,marco_id,equipe_id,hackathon_id,submissao_id,"
        "tipo_marco,repositorio_url,repositorio_validado_em,relatorio_pdf)"
        " VALUES(:en,:m,:e,:h,:p,'FINAL','https://github.com/a/b',now(),'\\x25504446')",
        en=entrega,
        m=final,
        e=s.equipes[0],
        h=s.h,
        p=proposta,
    )
    try:
        assert ler(client, cenario.mentor, s.equipes[0], "historico").json() == []
        # Feedback sobre o marco final continua possível.
        assert (
            escrever(client, cenario.mentor, s.equipes[0], marco_id=str(final)).status_code == 201
        )
    finally:
        sql("DELETE FROM submissoes_finais WHERE equipe_id=:e", e=s.equipes[0])


def test_marco_com_feedback_nao_pode_ser_excluido(client, s, cenario, calendario):
    marco = calendario.marco("Protótipo", 5)
    criar(client, cenario, s, marco_id=str(marco))
    resposta = client.delete(
        f"/admin/hackathons/{s.h}/mentoria/marcos/{marco}", headers=headers(s.cientifico)
    )
    assert resposta.status_code == 409
