"""
Autodeclaração de vínculo e comprovantes individuais por tipo (BE-S5-03).

Cobre estudantes, profissionais e mistos, recusa e reenvio, autorização estrita, documentos
privados, auditoria, política por edição e concorrência. Os testes gravam no banco de verdade; a
fixture `decl` apaga o que cria (usuários e e-mails saem pelas fixtures de conftest.py).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.exc import IntegrityError

from tests.test_convites import com_token
from tests.test_inscricao import CenarioInscricao
from tests.test_migrations import novo_hackathon, novo_usuario, rodar
from tests.test_migrations import sql as sql_na_transacao

URL_PRIVADA = "https://res.cloudinary.com/demo/segredo-do-integrante.pdf"
ESTUDANTE = {
    "tipo": "ESTUDANTE",
    "instituicao": "UFPA",
    "curso": "Sistemas de Informação",
    "periodo": 5,
}
PROFISSIONAL = {"tipo": "PROFISSIONAL", "organizacao": "Açaí Valley", "cargo": "Engenheira"}


class CenarioDeclaracao(CenarioInscricao):
    """Equipe de três integrantes na única edição aberta do cenário legado."""

    def criar_hackathon(self, **campos):
        id_ = self.sql(
            "INSERT INTO hackathon (nome, status, data_inicio) VALUES"
            " ('Teste de autodeclaração', 'INSCRICOES', '2099-06-01') RETURNING id"
        )[0]["id"]
        self.hackathons.append(id_)
        return id_

    def configurar_edicao(self, **campos):
        atribuicoes = ", ".join(f"{campo} = :{campo}" for campo in campos)
        self.sql(f"UPDATE hackathon SET {atribuicoes} WHERE id = :h", h=self.hackathon_id, **campos)

    def tornar(self, categoria: str, tipos: list[tuple[dict, str]]):
        """Define a categoria da equipe e o tipo indicado pelo líder para cada pessoa, dada como
        pares (usuário, tipo): o usuário é um dict, então não serve de chave."""
        self.sql(
            "UPDATE equipes SET categoria = CAST(:c AS categoria_equipe) WHERE id = :e",
            c=categoria,
            e=self.equipe_id,
        )
        for pessoa, tipo in tipos:
            self.sql(
                "UPDATE membros_equipe SET tipo_integrante = CAST(:t AS tipo_integrante)"
                " WHERE equipe_id = :e AND usuario_id = :u",
                t=tipo,
                e=self.equipe_id,
                u=pessoa["id"],
            )

    def comprovante_tipo(self, usuario, tipo, status="APROVADO", url="https://x.com/c.pdf"):
        validado = "NULL" if status == "PENDENTE" else "now()"
        return self.sql(
            "INSERT INTO comprovantes_vinculo (usuario_id, hackathon_id, arquivo_url, status,"
            " tipo_vinculo, validado_em) VALUES (:u, :h, :url, CAST(:s AS status_comprovante),"
            f" CAST(:t AS tipo_integrante), {validado}) RETURNING id",
            u=usuario["id"],
            h=self.hackathon_id,
            url=url,
            s=status,
            t=tipo,
        )[0]["id"]

    def declarar(self, client, quem, **corpo):
        return client.put("/me/autodeclaracao", headers=com_token(quem["id"]), json=corpo)

    def situacao(self, client, quem):
        return client.get("/me/autodeclaracao", headers=com_token(quem["id"]))

    def declaracoes(self, usuario) -> list[dict]:
        return self.sql(
            "SELECT * FROM autodeclaracoes_vinculo WHERE usuario_id = :u ORDER BY declarada_em, id",
            u=usuario["id"],
        )

    def enviar_comprovante(self, client, quem, url=URL_PRIVADA):
        return client.post(
            "/comprovantes", headers=com_token(quem["id"]), json={"arquivo_url": url}
        )

    def aprovar(self, client, comprovante_id, validador=None):
        validador = validador or self.organizador
        return client.post(
            f"/admin/comprovantes/{comprovante_id}/aprovar", headers=com_token(validador["id"])
        )

    def recusar(self, client, comprovante_id, motivo="Documento ilegível"):
        return client.post(
            f"/admin/comprovantes/{comprovante_id}/recusar",
            headers=com_token(self.organizador["id"]),
            json={"motivo_recusa": motivo},
        )

    def pendencias(self, client) -> list[dict]:
        return self.painel(client).json()["pendencias"]

    def codigos(self, client, pessoa=None) -> set[str]:
        return {
            p["codigo"]
            for p in self.pendencias(client)
            if pessoa is None or p["usuario_id"] == str(pessoa["id"])
        }

    def limpar(self):
        for h in self.hackathons:
            self.sql("DELETE FROM comprovantes_vinculo WHERE hackathon_id = :h", h=h)
            self.sql("DELETE FROM autodeclaracoes_vinculo WHERE hackathon_id = :h", h=h)
        super().limpar()


@pytest.fixture
def decl(sql, usuario_no_banco, novo_email, sem_edicoes_abertas):
    cenario = CenarioDeclaracao(sql, usuario_no_banco, novo_email)
    cenario.organizador = usuario_no_banco(papel="ORGANIZADOR")
    yield cenario
    cenario.limpar()


# --- Declarar o próprio vínculo -----------------------------------------------------------------


def test_participante_declara_estudante_e_profissional(client, decl):
    estudante, profissional = decl.usuario_no_banco(), decl.usuario_no_banco()

    a = decl.declarar(client, estudante, **ESTUDANTE)
    b = decl.declarar(client, profissional, **PROFISSIONAL)

    assert a.status_code == 200, a.text
    assert (a.json()["tipo"], a.json()["curso"], a.json()["periodo"]) == (
        "ESTUDANTE",
        "Sistemas de Informação",
        5,
    )
    assert a.json()["organizacao"] is None and a.json()["hackathon_id"] == str(decl.hackathon_id)
    assert b.status_code == 200, b.text
    assert (b.json()["organizacao"], b.json()["cargo"], b.json()["curso"]) == (
        "Açaí Valley",
        "Engenheira",
        None,
    )
    assert len(decl.declaracoes(estudante)) == 1 and len(decl.declaracoes(profissional)) == 1


@pytest.mark.parametrize(
    "corpo",
    [
        {"tipo": "ESTUDANTE", "instituicao": "UFPA", "periodo": 5},
        {**ESTUDANTE, "cargo": "Dev"},
        {**ESTUDANTE, "periodo": 0},
        {"tipo": "PROFISSIONAL", "organizacao": "Empresa"},
        {**PROFISSIONAL, "periodo": 3},
        {**PROFISSIONAL, "instituicao": "UFPA"},
        {"tipo": "ESTAGIARIO", "organizacao": "x", "cargo": "y"},
        {**ESTUDANTE, "curso": "   "},
        {**ESTUDANTE, "usuario_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
        {**ESTUDANTE, "hackathon_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
        {**ESTUDANTE, "status": "APROVADO"},
        {},
    ],
    ids=[
        "estudante-sem-curso",
        "estudante-com-cargo",
        "periodo-zero",
        "profissional-sem-cargo",
        "profissional-com-periodo",
        "profissional-com-instituicao",
        "tipo-invalido",
        "curso-em-branco",
        "com-usuario_id",
        "com-hackathon_id",
        "com-status",
        "vazio",
    ],
)
def test_declaracao_invalida_da_422_e_nao_grava(client, decl, corpo):
    pessoa = decl.usuario_no_banco()

    assert decl.declarar(client, pessoa, **corpo).status_code == 422
    assert decl.declaracoes(pessoa) == []


def test_mudar_a_declaracao_grava_linha_nova_e_repetir_nao_grava(client, decl):
    pessoa = decl.usuario_no_banco()
    assert decl.declarar(client, pessoa, **ESTUDANTE).status_code == 200
    assert decl.declarar(client, pessoa, **ESTUDANTE).status_code == 200  # igual: nada novo
    assert len(decl.declaracoes(pessoa)) == 1

    nova = {**ESTUDANTE, "periodo": 6}
    assert decl.declarar(client, pessoa, **nova).status_code == 200
    assert decl.declarar(client, pessoa, **PROFISSIONAL).status_code == 200

    historico = decl.declaracoes(pessoa)
    assert [(d["tipo"], d["periodo"]) for d in historico] == [
        ("ESTUDANTE", 5),
        ("ESTUDANTE", 6),
        ("PROFISSIONAL", None),
    ]
    situacao = decl.situacao(client, pessoa).json()
    assert situacao["atual"]["tipo"] == "PROFISSIONAL"
    assert [d["tipo"] for d in situacao["historico"]] == ["PROFISSIONAL", "ESTUDANTE", "ESTUDANTE"]


def test_banco_barra_alterar_declaracao_gravada_e_declaracao_incompleta():
    async def verificar(conn):
        hackathon, usuario = await novo_hackathon(conn), await novo_usuario(conn)
        declaracao = await sql_na_transacao(
            conn,
            "INSERT INTO autodeclaracoes_vinculo (usuario_id, hackathon_id, tipo, organizacao,"
            " cargo) VALUES (:u, :h, 'PROFISSIONAL', 'Empresa', 'Dev') RETURNING id",
            u=usuario,
            h=hackathon,
        )
        with pytest.raises(IntegrityError, match="autodeclaracao_imutavel"):
            async with conn.begin_nested():
                await sql_na_transacao(
                    conn,
                    "UPDATE autodeclaracoes_vinculo SET cargo = 'Chefe' WHERE id = :i",
                    i=declaracao,
                )
        with pytest.raises(IntegrityError, match="ck_autodeclaracoes_estudante"):
            async with conn.begin_nested():
                await sql_na_transacao(
                    conn,
                    "INSERT INTO autodeclaracoes_vinculo (usuario_id, hackathon_id, tipo,"
                    " instituicao) VALUES (:u, :h, 'ESTUDANTE', 'UFPA')",
                    u=usuario,
                    h=hackathon,
                )
        with pytest.raises(IntegrityError, match="ck_autodeclaracoes_profissional"):
            async with conn.begin_nested():
                await sql_na_transacao(
                    conn,
                    "INSERT INTO autodeclaracoes_vinculo (usuario_id, hackathon_id, tipo,"
                    " organizacao, cargo, periodo) VALUES (:u, :h, 'PROFISSIONAL', 'E', 'C', 2)",
                    u=usuario,
                    h=hackathon,
                )

    rodar(verificar)


# --- Autorização estrita ------------------------------------------------------------------------


def test_so_o_proprio_usuario_declara_e_a_declaracao_do_lider_nao_vale_para_outro(client, decl):
    pessoas = decl.montar(client)
    lider, membro = pessoas[0], pessoas[1]

    assert decl.declarar(client, lider, **PROFISSIONAL).status_code == 200

    assert decl.declaracoes(membro) == []
    assert decl.situacao(client, membro).json()["atual"] is None
    # Não há rota nem campo para declarar por outra pessoa
    por_terceiro = decl.declarar(client, lider, **ESTUDANTE, usuario_id=str(membro["id"]))
    assert por_terceiro.status_code == 422
    assert decl.declaracoes(membro) == []


@pytest.mark.parametrize("papel", ["ORGANIZADOR", "MENTOR", "COMITE_CIENTIFICO", "COMITE_TECNICO"])
def test_so_participante_declara(client, decl, usuario_no_banco, papel):
    outro = usuario_no_banco(papel=papel)

    assert decl.declarar(client, outro, **ESTUDANTE).status_code == 403
    assert decl.situacao(client, outro).status_code == 403
    assert decl.declaracoes(outro) == []


def test_sem_token_conta_pendente_e_dev(client, decl, usuario_no_banco):
    assert client.put("/me/autodeclaracao", json=ESTUDANTE).status_code == 401
    assert client.get("/me/autodeclaracao").status_code == 401
    pendente = usuario_no_banco(situacao_conta="PENDENTE")  # aguarda a conferência do comprovante
    dev = usuario_no_banco(papel="DEV")

    assert decl.declarar(client, pendente, **ESTUDANTE).status_code == 200
    assert decl.declarar(client, dev, **PROFISSIONAL).status_code == 200
    assert decl.situacao(client, pendente).status_code == 200


def test_sem_edicao_aberta_nao_declara(client, decl, monkeypatch):
    pessoa = decl.usuario_no_banco()

    async def nenhuma(db):
        return None

    # O banco de testes pode ter outras edições abertas: a busca é que não encontra nenhuma
    monkeypatch.setattr("app.services.edicao_participante.get_hackathon_com_inscricoes", nenhuma)

    assert decl.declarar(client, pessoa, **ESTUDANTE).status_code == 409
    assert decl.situacao(client, pessoa).status_code == 409
    assert decl.declaracoes(pessoa) == []


# --- Declarar não comprova ----------------------------------------------------------------------


def test_declaracao_e_comprovacao_ficam_separadas(client, decl):
    pessoa = decl.usuario_no_banco()
    decl.declarar(client, pessoa, **ESTUDANTE)

    antes = decl.situacao(client, pessoa).json()
    assert antes["atual"]["tipo"] == "ESTUDANTE"
    assert antes["vinculo_comprovado"] is False and antes["comprovante"] is None

    decl.comprovante_tipo(pessoa, "ESTUDANTE", "PENDENTE")
    pendente = decl.situacao(client, pessoa).json()
    assert pendente["comprovante"]["status"] == "PENDENTE"
    assert pendente["vinculo_comprovado"] is False

    decl.sql(
        "UPDATE comprovantes_vinculo SET status = 'APROVADO', validado_em = now()"
        " WHERE usuario_id = :u",
        u=pessoa["id"],
    )
    depois = decl.situacao(client, pessoa).json()
    assert depois["vinculo_comprovado"] is True
    assert depois["autodeclaracao_exigida"] is False and depois["comprovante_exigido"] is True
    assert "arquivo_url" not in decl.situacao(client, pessoa).text


def test_comprovante_de_outro_tipo_nao_comprova_o_vinculo_declarado(client, decl):
    pessoa = decl.usuario_no_banco()
    decl.declarar(client, pessoa, **PROFISSIONAL)
    decl.comprovante_tipo(pessoa, "ESTUDANTE")  # aprovado, mas é acadêmico

    situacao = decl.situacao(client, pessoa).json()

    assert situacao["comprovante"] is None and situacao["vinculo_comprovado"] is False


# --- Homologação por categoria ------------------------------------------------------------------


def test_equipe_de_estudantes_homologa_como_antes(client, decl):
    decl.montar(client, vinculos=True)

    assert decl.concluir(client).json()["situacao"] == "HOMOLOGADA"


def test_equipe_de_profissionais_so_homologa_com_comprovante_profissional(client, decl):
    pessoas = decl.montar(client)
    decl.tornar("PROFISSIONAIS", [(p, "PROFISSIONAL") for p in pessoas])
    for pessoa in pessoas:
        decl.comprovante_tipo(pessoa, "ESTUDANTE")  # aprovados, mas de outro vínculo

    assert decl.concluir(client).json()["situacao"] == "AGUARDANDO_HOMOLOGACAO"
    sem_comprovante = [
        p for p in decl.pendencias(client) if p["codigo"] == "COMPROVANTE_NAO_ENVIADO"
    ]
    assert len(sem_comprovante) == 3
    assert all("profissional" in p["mensagem"] for p in sem_comprovante)

    ultimo = len(pessoas) - 1
    for indice, pessoa in enumerate(pessoas):
        enviado = decl.enviar_comprovante(client, pessoa)
        assert enviado.status_code == 201, enviado.text
        assert enviado.json()["tipo_vinculo"] == "PROFISSIONAL"
        assert decl.aprovar(client, enviado.json()["id"]).status_code == 200
        esperado = "HOMOLOGADA" if indice == ultimo else "AGUARDANDO_HOMOLOGACAO"
        assert decl.equipe()["situacao"] == esperado


def test_equipe_mista_exige_cada_comprovante_do_tipo_de_cada_pessoa(client, decl):
    lider, estudante, profissional = decl.montar(client)
    decl.tornar(
        "MISTA",
        [(lider, "ESTUDANTE"), (estudante, "ESTUDANTE"), (profissional, "PROFISSIONAL")],
    )
    for pessoa in (lider, estudante, profissional):
        decl.comprovante_tipo(pessoa, "ESTUDANTE")

    assert decl.concluir(client).json()["situacao"] == "AGUARDANDO_HOMOLOGACAO"
    pendentes = [p for p in decl.pendencias(client) if p["codigo"].startswith("COMPROVANTE")]
    assert [p["usuario_id"] for p in pendentes] == [str(profissional["id"])]

    enviado = decl.enviar_comprovante(client, profissional)
    assert enviado.status_code == 201 and enviado.json()["tipo_vinculo"] == "PROFISSIONAL"
    assert decl.aprovar(client, enviado.json()["id"]).status_code == 200
    assert decl.equipe()["situacao"] == "HOMOLOGADA"


def test_politica_da_edicao_dispensa_o_comprovante_do_tipo(client, decl):
    pessoas = decl.montar(client)
    decl.tornar("PROFISSIONAIS", [(p, "PROFISSIONAL") for p in pessoas])
    decl.configurar_edicao(exige_comprovante_profissional=False)

    corpo = decl.concluir(client).json()

    assert corpo["situacao"] == "HOMOLOGADA"
    assert decl.codigos(client) == set()


def test_politica_da_edicao_dispensa_o_comprovante_do_estudante(client, decl):
    decl.montar(client)
    decl.configurar_edicao(exige_comprovante_estudante=False)

    assert decl.concluir(client).json()["situacao"] == "HOMOLOGADA"


def test_edicao_que_exige_autodeclaracao_so_homologa_com_a_de_todos(client, decl):
    pessoas = decl.montar(client, vinculos=True)
    decl.configurar_edicao(exige_autodeclaracao=True)

    assert decl.concluir(client).json()["situacao"] == "AGUARDANDO_HOMOLOGACAO"
    pendentes = [p for p in decl.pendencias(client) if p["codigo"] == "AUTODECLARACAO_PENDENTE"]
    assert {p["usuario_id"] for p in pendentes} == {str(p["id"]) for p in pessoas}
    assert all(p["bloqueia_conclusao"] is False for p in pendentes)

    for indice, pessoa in enumerate(pessoas):
        assert decl.declarar(client, pessoa, **ESTUDANTE).status_code == 200
        esperado = "HOMOLOGADA" if indice == len(pessoas) - 1 else "AGUARDANDO_HOMOLOGACAO"
        assert decl.equipe()["situacao"] == esperado


def test_declarar_tipo_diferente_do_indicado_tira_a_equipe_da_homologacao(client, decl):
    pessoas = decl.montar(client, vinculos=True)
    decl.configurar_edicao(exige_autodeclaracao=True)
    for pessoa in pessoas:
        decl.declarar(client, pessoa, **ESTUDANTE)
    assert decl.concluir(client).json()["situacao"] == "HOMOLOGADA"
    divergente = pessoas[1]

    assert decl.declarar(client, divergente, **PROFISSIONAL).status_code == 200

    assert decl.equipe()["situacao"] == "AGUARDANDO_HOMOLOGACAO"
    [pendencia] = [p for p in decl.pendencias(client) if p["codigo"] == "TIPO_DIVERGENTE"]
    assert pendencia["usuario_id"] == str(divergente["id"])
    assert "PROFISSIONAL" in pendencia["mensagem"] and "ESTUDANTE" in pendencia["mensagem"]
    composicao = client.get(
        f"/equipes/{decl.equipe_id}/composicao", headers=com_token(decl.lider["id"])
    ).json()
    por_conta = {
        i["confirmado_pelo_integrante"]["usuario_id"]: i["confirmado_pelo_integrante"]
        for i in composicao["integrantes"]
        if i["confirmado_pelo_integrante"]["integrante"]
    }
    assert por_conta[str(divergente["id"])]["tipo_declarado"] == "PROFISSIONAL"
    assert por_conta[str(divergente["id"])]["vinculo_comprovado"] is True  # o do tipo indicado

    # A pessoa revê a declaração e a equipe volta a homologar; nada foi apagado
    assert decl.declarar(client, divergente, **ESTUDANTE).status_code == 200
    assert decl.equipe()["situacao"] == "HOMOLOGADA"
    assert len(decl.declaracoes(divergente)) == 3


def test_lider_corrige_o_tipo_indicado_e_resolve_a_divergencia(client, decl):
    pessoas = decl.montar(client, vinculos=True)
    decl.configurar_edicao(exige_autodeclaracao=True)
    for pessoa in pessoas:
        decl.declarar(client, pessoa, **ESTUDANTE)
    decl.declarar(client, pessoas[2], **PROFISSIONAL)
    assert "TIPO_DIVERGENTE" in decl.codigos(client)

    decl.tornar("MISTA", [(pessoas[2], "PROFISSIONAL")])
    decl.comprovante_tipo(pessoas[2], "PROFISSIONAL")

    assert "TIPO_DIVERGENTE" not in decl.codigos(client)


# --- Recusa e reenvio ---------------------------------------------------------------------------


def test_recusa_e_reenvio_do_comprovante_profissional(client, decl):
    pessoas = decl.montar(client)
    profissional = pessoas[1]
    decl.tornar("MISTA", [(profissional, "PROFISSIONAL")])
    decl.comprovante_tipo(pessoas[0], "ESTUDANTE")
    decl.comprovante_tipo(pessoas[2], "ESTUDANTE")
    decl.declarar(client, profissional, **PROFISSIONAL)
    decl.concluir(client)

    primeiro = decl.enviar_comprovante(client, profissional)
    assert primeiro.status_code == 201, primeiro.text
    assert primeiro.json()["tipo_vinculo"] == "PROFISSIONAL"
    declaracao = decl.declaracoes(profissional)[0]
    assert primeiro.json()["autodeclaracao_id"] == str(declaracao["id"])
    assert decl.codigos(client, profissional) == {"COMPROVANTE_PENDENTE"}
    # Um comprovante em aberto do mesmo tipo impede outro; o histórico só cresce com a recusa
    assert decl.enviar_comprovante(client, profissional).status_code == 409

    recusa = decl.recusar(client, primeiro.json()["id"])
    assert recusa.status_code == 200 and recusa.json()["tipo_vinculo"] == "PROFISSIONAL"
    assert decl.codigos(client, profissional) == {"COMPROVANTE_RECUSADO"}
    meus = client.get("/comprovantes/meus", headers=com_token(profissional["id"])).json()
    assert meus[0]["motivo_recusa"] == "Documento ilegível"

    segundo = decl.enviar_comprovante(client, profissional)
    assert segundo.status_code == 201 and segundo.json()["id"] != primeiro.json()["id"]
    assert decl.codigos(client, profissional) == {"COMPROVANTE_PENDENTE"}
    assert decl.aprovar(client, segundo.json()["id"]).status_code == 200
    assert decl.codigos(client) == set()
    assert decl.equipe()["situacao"] == "HOMOLOGADA"
    historico = decl.sql(
        "SELECT status FROM comprovantes_vinculo WHERE usuario_id = :u AND tipo_vinculo ="
        " 'PROFISSIONAL' ORDER BY enviado_em",
        u=profissional["id"],
    )
    assert [c["status"] for c in historico] == ["RECUSADO", "APROVADO"]


def test_reenvio_simultaneo_gera_um_so_comprovante(client, decl):
    pessoas = decl.montar(client)
    decl.tornar("PROFISSIONAIS", [(p, "PROFISSIONAL") for p in pessoas])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(decl.enviar_comprovante, client, pessoas[1]) for _ in range(2)]
        codigos = sorted(f.result().status_code for f in futuros)

    assert codigos == [201, 409]


def test_conferente_ve_o_tipo_e_a_declaracao_ao_lado_do_documento(client, decl):
    profissional = decl.usuario_no_banco()
    decl.declarar(client, profissional, **PROFISSIONAL)
    enviado = decl.enviar_comprovante(client, profissional)
    assert enviado.status_code == 201, enviado.text

    fila = client.get(
        f"/admin/comprovantes?hackathon_id={decl.hackathon_id}",
        headers=com_token(decl.organizador["id"]),
    )

    [item] = fila.json()
    assert item["tipo_vinculo"] == "PROFISSIONAL"
    assert item["autodeclaracao"]["organizacao"] == "Açaí Valley"
    assert item["arquivo_url"] == URL_PRIVADA  # o conferente abre o documento


def test_so_conferente_ve_a_fila_de_comprovantes(client, decl):
    participante = decl.usuario_no_banco()

    assert (
        client.get("/admin/comprovantes", headers=com_token(participante["id"])).status_code == 403
    )
    assert (
        decl.aprovar(client, "3fa85f64-5717-4562-b3fc-2c963f66afa6", participante).status_code
        == 403
    )


# --- Documentos privados ------------------------------------------------------------------------


def test_o_link_do_documento_so_chega_ao_dono_e_ao_conferente(client, decl):
    pessoas = decl.montar(client)
    dono, lider = pessoas[1], pessoas[0]
    decl.comprovante_tipo(dono, "ESTUDANTE", "PENDENTE", url=URL_PRIVADA)
    decl.declarar(client, dono, **ESTUDANTE)
    decl.concluir(client)
    cabecalho = com_token(lider["id"])
    equipe = decl.equipe_id

    respostas = [
        client.get(f"/equipes/{equipe}/painel", headers=cabecalho),
        client.get(f"/equipes/{equipe}/composicao", headers=cabecalho),
        client.get(f"/equipes/{equipe}/membros", headers=cabecalho),
        client.get(f"/equipes/{equipe}/convites", headers=cabecalho),
        client.get("/comprovantes/meus", headers=cabecalho),
        client.get("/me/autodeclaracao", headers=cabecalho),
        client.get("/me/autodeclaracao", headers=com_token(dono["id"])),
    ]

    for resposta in respostas:
        assert resposta.status_code == 200, resposta.text
        assert "segredo-do-integrante" not in resposta.text
    proprio = client.get("/comprovantes/meus", headers=com_token(dono["id"]))
    assert URL_PRIVADA in proprio.text


# --- Política da edição e concorrência ----------------------------------------------------------


def test_organizador_configura_a_politica_de_verificacao(client, decl):
    url = f"/admin/hackathons/{decl.hackathon_id}"
    cabecalho = com_token(decl.organizador["id"])

    ok = client.patch(
        url,
        headers=cabecalho,
        json={"exige_autodeclaracao": True, "exige_comprovante_profissional": False},
    )

    assert ok.status_code == 200, ok.text
    assert ok.json()["exige_autodeclaracao"] is True
    assert ok.json()["exige_comprovante_profissional"] is False
    assert ok.json()["exige_comprovante_estudante"] is True
    nulo = client.patch(url, headers=cabecalho, json={"exige_comprovante_estudante": None})
    assert nulo.status_code == 422


def test_declaracoes_simultaneas_iguais_viram_uma_e_diferentes_viram_duas(client, decl):
    igual, diferente = decl.usuario_no_banco(), decl.usuario_no_banco()

    with ThreadPoolExecutor(max_workers=4) as pool:
        iguais = [pool.submit(decl.declarar, client, igual, **ESTUDANTE) for _ in range(2)]
        outras = [
            pool.submit(decl.declarar, client, diferente, **{**ESTUDANTE, "periodo": p})
            for p in (3, 4)
        ]
        codigos = [f.result().status_code for f in iguais + outras]

    assert codigos == [200, 200, 200, 200]
    assert len(decl.declaracoes(igual)) == 1
    assert len(decl.declaracoes(diferente)) == 2


def test_migration_comprovante_por_tipo_e_defaults_legados():
    async def verificar(conn):
        hackathon, usuario = await novo_hackathon(conn), await novo_usuario(conn)
        inserir = (
            "INSERT INTO comprovantes_vinculo (usuario_id, hackathon_id, arquivo_url{col})"
            " VALUES (:u, :h, 'https://x.com/c.pdf'{val}) RETURNING id"
        )
        legado = await sql_na_transacao(
            conn, inserir.format(col="", val=""), u=usuario, h=hackathon
        )
        assert (
            await sql_na_transacao(
                conn, "SELECT tipo_vinculo::text FROM comprovantes_vinculo WHERE id = :i", i=legado
            )
            == "ESTUDANTE"
        )
        # Outro tipo convive com o acadêmico; o mesmo tipo em aberto continua barrado
        await sql_na_transacao(
            conn,
            inserir.format(col=", tipo_vinculo", val=", 'PROFISSIONAL'"),
            u=usuario,
            h=hackathon,
        )
        with pytest.raises(IntegrityError, match="uq_comprovantes_vinculo_ativo"):
            async with conn.begin_nested():
                await sql_na_transacao(conn, inserir.format(col="", val=""), u=usuario, h=hackathon)
        padrao = await sql_na_transacao(
            conn,
            "SELECT exige_autodeclaracao = false AND exige_comprovante_estudante"
            " AND exige_comprovante_profissional FROM hackathon WHERE id = :h",
            h=hackathon,
        )
        assert padrao is True

    rodar(verificar)


def test_swagger_documenta_a_autodeclaracao(client):
    documento = client.get("/openapi.json").json()
    for metodo in ("get", "put"):
        rota = documento["paths"]["/me/autodeclaracao"][metodo]
        assert rota["tags"] == ["Autodeclaração"] and rota["security"]
        assert {"401", "403", "409"} <= set(rota["responses"])
    assert "422" in documento["paths"]["/me/autodeclaracao"]["put"]["responses"]
    esquemas = documento["components"]["schemas"]
    assert esquemas["AutodeclaracaoEnvio"]["additionalProperties"] is False
    assert "arquivo_url" not in esquemas["AutodeclaracaoSituacaoResponse"]["properties"]
    assert "arquivo_url" not in esquemas["ComprovacaoResumo"]["properties"]
