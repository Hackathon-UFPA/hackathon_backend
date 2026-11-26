"""BE-S6-04: painel do mentor, agregação, escopo de visibilidade e ausência de vazamentos."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.const.enums import TipoMarcoMentoria
from app.models import EntregaMentoria, MarcoMentoria
from app.schemas.painel_mentor import SituacaoMarcoEquipe
from app.services.painel_mentor import situacao_do_marco
from tests.test_atribuicoes_mentor import atribuir, headers, s, substituir, url

__all__ = ["s"]  # fixture reaproveitada: edição homologada, 3 equipes (2 aprovadas)

PAINEL = "/me/mentoria/painel"


@pytest.fixture
def calendario(s, sql):
    """Cria marcos e entregas direto no banco, o que permite prazos já vencidos. Depende de `s`
    para limpar antes que ela apague edições e equipes."""
    edicoes: set = set()

    def marco(titulo, dias, *, hackathon_id=None, tipo="PARCIAL"):
        hackathon_id = hackathon_id or s.h
        edicoes.add(hackathon_id)
        return sql(
            "INSERT INTO marcos_mentoria(id,hackathon_id,titulo,descricao,data_limite,tipo)"
            " VALUES(:id,:h,:t,'Instruções',:prazo,CAST(:tipo AS tipo_marco_mentoria))"
            " RETURNING id",
            id=uuid4(),
            h=hackathon_id,
            t=titulo,
            prazo=datetime.now(UTC) + timedelta(days=dias),
            tipo=tipo,
        )[0]["id"]

    def entrega(marco_id, equipe_id, autor_id):
        sql(
            "INSERT INTO entregas_mentoria(id,marco_id,equipe_id,hackathon_id,enviado_por,"
            "enviado_em,data_limite_no_envio,descricao,referencias)"
            " SELECT :id,m.id,:e,m.hackathon_id,:autor,m.data_limite - interval '1 day',"
            "m.data_limite,'Fluxo pronto','{https://exemplo.com/repo}'"
            " FROM marcos_mentoria m WHERE m.id=:m",
            id=uuid4(),
            m=marco_id,
            e=equipe_id,
            autor=autor_id,
        )

    yield SimpleNamespace(marco=marco, entrega=entrega)
    for tabela in ("entregas_mentoria", "marcos_mentoria"):
        sql(f"DELETE FROM {tabela} WHERE hackathon_id=ANY(:hs)", hs=list(edicoes))


@pytest.fixture
def organizacao(sql):
    """Organizações temporárias; desvincula edições e usuários antes de apagá-las."""
    ids = []

    def criar():
        ids.append(
            sql(
                "INSERT INTO organizacoes(nome,tipo) VALUES('Org do painel','EMPRESA') RETURNING id"
            )[0]["id"]
        )
        return ids[-1]

    yield criar
    for tabela in ("hackathon", "usuarios"):
        sql(f"UPDATE {tabela} SET organizacao_id=NULL WHERE organizacao_id=ANY(:ids)", ids=ids)
    sql("DELETE FROM organizacoes WHERE id=ANY(:ids)", ids=ids)


def acompanhar(client, s, mentor, equipe=None):
    resposta = atribuir(client, s, mentor, equipe)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def consultar(client, usuario, caminho="", **params):
    return client.get(PAINEL + caminho, headers=headers(usuario), params=params)


def painel(client, usuario, **params):
    resposta = consultar(client, usuario, **params)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def detalhe(client, usuario, equipe_id):
    return consultar(client, usuario, f"/equipes/{equipe_id}")


def ids_das_equipes(corpo):
    return [equipe["equipe_id"] for equipe in corpo["equipes"]]


def assert_fora_do_escopo(client, mentor, equipe_id):
    assert str(equipe_id) not in ids_das_equipes(painel(client, mentor))
    assert painel(client, mentor, equipe_id=str(equipe_id))["total"] == 0
    resposta = detalhe(client, mentor, equipe_id)
    assert resposta.status_code == 404
    # A mesma resposta de uma equipe que não existe: não confirma a existência de nenhuma.
    assert resposta.json() == detalhe(client, mentor, uuid4()).json()


def montar_calendario(calendario, s):
    """Um marco entregue pela primeira equipe, um vencido, dois futuros e o final."""
    autor = s.membro()
    entregue = calendario.marco("Entregue", -10)
    calendario.entrega(entregue, s.equipes[0], autor["id"])
    return SimpleNamespace(
        autor=autor,
        entregue=entregue,
        vencido=calendario.marco("Vencido", -5),
        distante=calendario.marco("Distante", 20),
        proximo=calendario.marco("Próximo", 5),
        final=calendario.marco("Final", 30, tipo="FINAL"),
    )


def test_painel_agrega_progresso_e_pendencias(client, s, calendario):
    mentor = s.mentor()
    for equipe in s.equipes[:2]:
        acompanhar(client, s, mentor, equipe)
    marcos = montar_calendario(calendario, s)

    corpo = painel(client, mentor)

    assert corpo["total"] == 2
    assert corpo["resumo"] == {
        "total": 8,
        "entregues": 1,
        "pendentes": 4,
        "nao_entregues": 3,
        "equipes_com_nao_entregues": 2,
        "equipes_sem_feedback": 2,
    }
    assert ids_das_equipes(corpo) == [str(e) for e in s.equipes[:2]]  # ordem por nome
    primeira, segunda = corpo["equipes"]
    assert primeira["equipe_nome"] == "Equipe 0"
    assert primeira["hackathon_id"] == str(s.h)
    assert primeira["progresso"] == {
        "total": 4,
        "entregues": 1,
        "pendentes": 2,
        "nao_entregues": 1,
    }
    assert primeira["proximo_marco"]["id"] == str(marcos.proximo)
    # A entrega de uma equipe não conta para a outra.
    assert segunda["progresso"] == {
        "total": 4,
        "entregues": 0,
        "pendentes": 2,
        "nao_entregues": 2,
    }


def test_edicao_sem_calendario(client, s):
    mentor = s.mentor()
    acompanhar(client, s, mentor)
    [equipe] = painel(client, mentor)["equipes"]
    assert equipe["progresso"] == {"total": 0, "entregues": 0, "pendentes": 0, "nao_entregues": 0}
    assert equipe["proximo_marco"] is None
    assert detalhe(client, mentor, s.equipes[0]).json()["marcos"] == []


def test_mentor_sem_equipes(client, s):
    corpo = painel(client, s.mentor())
    assert corpo["total"] == 0 and corpo["equipes"] == []
    assert set(corpo["resumo"].values()) == {0}


def test_paginacao_mantem_resumo_de_todas_as_equipes(client, s, calendario):
    mentor = s.mentor()
    for equipe in s.equipes[:2]:
        acompanhar(client, s, mentor, equipe)
    montar_calendario(calendario, s)
    completo = painel(client, mentor)

    paginas = [painel(client, mentor, limite=1, deslocamento=n) for n in range(3)]

    assert [ids_das_equipes(p) for p in paginas] == [
        [str(s.equipes[0])],
        [str(s.equipes[1])],
        [],
    ]
    assert all(p["total"] == 2 and p["resumo"] == completo["resumo"] for p in paginas)
    assert (paginas[1]["limite"], paginas[1]["deslocamento"]) == (1, 1)


@pytest.mark.parametrize(
    "params",
    [{"limite": 0}, {"limite": 101}, {"deslocamento": -1}, {"equipe_id": "abc"}],
)
def test_parametros_invalidos(client, s, params):
    assert consultar(client, s.mentor(), **params).status_code == 422


def test_filtros_por_edicao_e_equipe(client, s, sql):
    outra = s.edicao()
    mentor = s.mentor(cap=3)
    for termo in outra.termos:
        sql(
            "INSERT INTO aceites_termos(termo_id,usuario_id) VALUES(:t,:u)", t=termo, u=mentor["id"]
        )
    acompanhar(client, s, mentor)
    acompanhar(client, s, mentor, outra.equipes[0])

    assert painel(client, mentor)["total"] == 2
    por_edicao = painel(client, mentor, hackathon_id=str(outra.h))
    assert ids_das_equipes(por_edicao) == [str(outra.equipes[0])]
    por_equipe = painel(client, mentor, equipe_id=str(s.equipes[0]))
    assert ids_das_equipes(por_equipe) == [str(s.equipes[0])]
    cruzado = painel(client, mentor, hackathon_id=str(outra.h), equipe_id=str(s.equipes[0]))
    assert cruzado["total"] == 0
    assert painel(client, mentor, hackathon_id=str(uuid4()))["total"] == 0


def test_detalhe_traz_integrantes_calendario_e_entregas(client, s, sql, calendario):
    mentor = s.mentor()
    acompanhar(client, s, mentor)
    marcos = montar_calendario(calendario, s)
    sql("UPDATE usuarios SET nome='Integrante' WHERE id=:u", u=marcos.autor["id"])

    resposta = detalhe(client, mentor, s.equipes[0])

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["integrantes"] == [{"nome": "Integrante", "funcao": "DESENVOLVEDOR"}]
    assert [(m["titulo"], m["situacao"]) for m in corpo["marcos"]] == [
        ("Entregue", "ENTREGUE"),
        ("Vencido", "NAO_ENTREGUE"),
        ("Próximo", "PENDENTE"),
        ("Distante", "PENDENTE"),
        ("Final", None),
    ]
    entrega = corpo["marcos"][0]["entrega"]
    assert entrega["descricao"] == "Fluxo pronto"
    assert entrega["referencias"] == ["https://exemplo.com/repo"]
    assert all(m["entrega"] is None for m in corpo["marcos"][1:])
    [resumo] = painel(client, mentor)["equipes"]
    assert {campo: corpo[campo] for campo in resumo} == resumo


@pytest.mark.parametrize("status", ["FINALIZADO", "CANCELADO"])
def test_edicao_encerrada_nao_tem_pendencias_em_aberto(client, s, sql, calendario, status):
    mentor = s.mentor()
    acompanhar(client, s, mentor)
    montar_calendario(calendario, s)
    sql("UPDATE hackathon SET status=CAST(:s AS status_hackathon) WHERE id=:h", s=status, h=s.h)

    [equipe] = painel(client, mentor)["equipes"]

    assert equipe["hackathon_status"] == status
    assert equipe["progresso"] == {"total": 4, "entregues": 1, "pendentes": 0, "nao_entregues": 3}
    assert equipe["proximo_marco"] is None


def test_nao_vaza_dados_sensiveis(client, s, sql, calendario):
    mentor = s.mentor()
    acompanhar(client, s, mentor)
    marcos = montar_calendario(calendario, s)
    sql(
        "UPDATE usuarios SET instituicao='Instituição sigilosa' WHERE id=:u",
        u=marcos.autor["id"],
    )

    respostas = [consultar(client, mentor), detalhe(client, mentor, s.equipes[0])]

    def chaves(valor):
        if isinstance(valor, dict):
            return set(valor) | {c for item in valor.values() for c in chaves(item)}
        if isinstance(valor, list):
            return {c for item in valor for c in chaves(item)}
        return set()

    proibidas = {
        "email",
        "usuario_id",
        "mentor_id",
        "enviado_por",
        "atribuido_por",
        "motivo",
        "nota_media",
        "classificacao",
        "aprovada",
        "pareceres",
        "submissao_id",
        "instituicao",
        "senha_hash",
    }
    for resposta in respostas:
        assert resposta.status_code == 200, resposta.text
        assert not chaves(resposta.json()) & proibidas
        for valor in (
            marcos.autor["email"],
            str(marcos.autor["id"]),
            mentor["email"],
            "Instituição sigilosa",
            str(s.organizador["id"]),
        ):
            assert valor not in resposta.text


def test_equipe_nao_designada_e_de_outro_mentor(client, s):
    mentor, colega = s.mentor(), s.mentor()
    acompanhar(client, s, mentor)
    acompanhar(client, s, colega, s.equipes[1])

    assert ids_das_equipes(painel(client, mentor)) == [str(s.equipes[0])]
    assert_fora_do_escopo(client, mentor, s.equipes[1])  # de outro mentor
    assert_fora_do_escopo(client, mentor, s.equipes[2])  # sem mentor


def test_mentor_substituido_perde_o_acesso_e_o_novo_ve_o_historico(client, s, calendario):
    anterior, novo = s.mentor(), s.mentor()
    atual = acompanhar(client, s, anterior)
    montar_calendario(calendario, s)

    assert substituir(client, s, novo, atual).status_code == 200

    assert_fora_do_escopo(client, anterior, s.equipes[0])
    assert painel(client, anterior)["resumo"]["total"] == 0
    assert painel(client, novo)["resumo"]["entregues"] == 1
    assert detalhe(client, novo, s.equipes[0]).status_code == 200


def test_atribuicao_encerrada(client, s):
    mentor = s.mentor()
    atual = acompanhar(client, s, mentor)
    resposta = client.post(
        url(s.equipes[0]) + "/encerrar",
        headers=headers(s.cientifico),
        json={"atribuicao_atual_id": atual["id"], "motivo": "Fim do acompanhamento"},
    )
    assert resposta.status_code == 200
    assert_fora_do_escopo(client, mentor, s.equipes[0])


@pytest.mark.parametrize(
    "comando",
    [
        "UPDATE equipes SET situacao='NAO_HOMOLOGADA' WHERE id=:e",
        "UPDATE equipes SET situacao='AGUARDANDO_HOMOLOGACAO' WHERE id=:e",
        "DELETE FROM resultados_proposta WHERE equipe_id=:e",
    ],
    ids=["nao-homologada", "aguardando-homologacao", "sem-resultado"],
)
def test_equipe_que_deixou_de_ser_elegivel(client, s, sql, comando):
    mentor = s.mentor()
    acompanhar(client, s, mentor)
    sql(comando, e=s.equipes[0])
    assert_fora_do_escopo(client, mentor, s.equipes[0])


def test_equipe_reprovada_nao_aparece_mesmo_com_vinculo_no_banco(client, s, sql):
    mentor = s.mentor()
    reprovada = s.equipes[2]
    # A API recusa esta atribuição; o vínculo direto prova que o painel confere o resultado.
    sql(
        "INSERT INTO atribuicoes_mentor(id,equipe_id,hackathon_id,mentor_id,atribuido_por)"
        " VALUES(:id,:e,:h,:m,:autor)",
        id=uuid4(),
        e=reprovada,
        h=s.h,
        m=mentor["id"],
        autor=s.cientifico["id"],
    )
    assert_fora_do_escopo(client, mentor, reprovada)


def test_isolamento_entre_organizacoes(client, s, sql, organizacao):
    propria, alheia = organizacao(), organizacao()
    mentor = s.mentor()
    acompanhar(client, s, mentor)
    sql("UPDATE usuarios SET organizacao_id=:o WHERE id=:u", o=propria, u=mentor["id"])
    sql("UPDATE hackathon SET organizacao_id=:o WHERE id=:h", o=propria, h=s.h)
    assert ids_das_equipes(painel(client, mentor)) == [str(s.equipes[0])]

    # Mesmo com um vínculo vigente no banco, a edição de outra organização não aparece.
    sql("UPDATE hackathon SET organizacao_id=:o WHERE id=:h", o=alheia, h=s.h)

    assert_fora_do_escopo(client, mentor, s.equipes[0])


def test_exige_autenticacao(client):
    assert client.get(PAINEL).status_code == 401
    assert client.get(f"{PAINEL}/equipes/{uuid4()}").status_code == 401


@pytest.mark.parametrize(
    "papel", ["PARTICIPANTE", "ORGANIZADOR", "COMITE_CIENTIFICO", "COMITE_TECNICO"]
)
def test_perfis_sem_acesso(client, s, usuario_no_banco, papel):
    usuario = usuario_no_banco(papel=papel, senha=None)
    assert consultar(client, usuario).status_code == 403
    assert detalhe(client, usuario, s.equipes[0]).status_code == 403


def test_mentor_pendente_ou_desativado(client, s, sql):
    assert consultar(client, s.mentor(concluido=False)).status_code == 403
    mentor = s.mentor()
    acompanhar(client, s, mentor)
    sql("UPDATE usuarios SET ativo=false WHERE id=:u", u=mentor["id"])
    assert consultar(client, mentor).status_code == 401
    assert detalhe(client, mentor, s.equipes[0]).status_code == 401


def test_dev_ve_apenas_os_proprios_vinculos(client, s, usuario_no_banco):
    acompanhar(client, s, s.mentor())
    dev = usuario_no_banco(papel="DEV", senha=None)
    assert painel(client, dev)["total"] == 0
    assert detalhe(client, dev, s.equipes[0]).status_code == 404


@pytest.mark.parametrize(
    ("atraso", "encerrada", "tipo", "esperada"),
    [
        (timedelta(seconds=-1), False, "PARCIAL", SituacaoMarcoEquipe.PENDENTE),
        (timedelta(0), False, "PARCIAL", SituacaoMarcoEquipe.PENDENTE),  # prazo inclusivo
        (timedelta(seconds=1), False, "PARCIAL", SituacaoMarcoEquipe.NAO_ENTREGUE),
        (timedelta(seconds=-1), True, "PARCIAL", SituacaoMarcoEquipe.NAO_ENTREGUE),
        (timedelta(seconds=1), True, "FINAL", None),
    ],
)
def test_situacao_do_marco_sem_entrega(atraso, encerrada, tipo, esperada):
    prazo = datetime(2026, 12, 1, tzinfo=UTC)
    marco = MarcoMentoria(data_limite=prazo, tipo=TipoMarcoMentoria(tipo))
    situacao = situacao_do_marco(marco, None, edicao_encerrada=encerrada, agora=prazo + atraso)
    assert situacao == esperada


@pytest.mark.parametrize("tipo", list(TipoMarcoMentoria))
def test_situacao_do_marco_com_entrega(tipo):
    prazo = datetime(2026, 12, 1, tzinfo=UTC)
    marco = MarcoMentoria(data_limite=prazo, tipo=tipo)
    situacao = situacao_do_marco(
        marco, EntregaMentoria(), edicao_encerrada=True, agora=prazo + timedelta(days=1)
    )
    assert situacao == SituacaoMarcoEquipe.ENTREGUE
