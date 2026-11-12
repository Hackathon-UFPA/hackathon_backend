"""BE-S5-09: reenvio/versionamento da proposta (RF27, RN08), protocolo por versão e travas
entre envio, distribuição e homologação do resultado (RF31)."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Thread
from uuid import uuid4

import asyncpg
import pytest

from app.const.config import settings
from tests.test_convites import com_token
from tests.test_envio_proposta import CenarioEnvio
from tests.test_resultado import CenarioResultado

NOVA_VERSAO = {
    "titulo": "Coleta seletiva 2.0",
    "descricao": "Nova descrição da solução",
    "ods": [11, 12],
    "bases_dados": "IBGE e INPE",
    "documento_url": "https://exemplo.org/proposta-v2.pdf",
}


class CenarioVersoes(CenarioEnvio):
    @property
    def url_reenvio(self):
        return f"{self.url_enviada}/reenviar"

    def reenviar(self, client, quem=None, **campos):
        dados = {"tema_id": str(self.tema_ativo), **NOVA_VERSAO, **campos}
        return client.post(
            self.url_reenvio, json=dados, headers=com_token((quem or self.lider)["id"])
        )

    def novo_tema(self, titulo, *, ativo=True):
        return self.sql(
            "INSERT INTO temas (hackathon_id, titulo, ativo) VALUES (:h, :t, :a) RETURNING id",
            h=self.hackathon_id,
            t=titulo,
            a=ativo,
        )[0]["id"]

    def versoes(self, client, quem=None):
        return client.get(
            f"{self.url_enviada}/versoes", headers=com_token((quem or self.lider)["id"])
        )

    def enviada(self, client) -> dict:
        self.preparar(client)
        resposta = self.enviar(client)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def prazo(self, *, aberto: bool):
        fim = "now() + interval '1 day'" if aberto else "now() - interval '1 hour'"
        self.sql(f"UPDATE hackathon SET propostas_fim = {fim} WHERE id = :h", h=self.hackathon_id)

    def designar(self, submissao_id):
        avaliador = self.usuario_no_banco(papel="COMITE_CIENTIFICO", senha=None)
        self.sql(
            "INSERT INTO designacoes_avaliacao (submissao_id, hackathon_id, avaliador_id)"
            " VALUES (:s, :h, :a)",
            s=submissao_id,
            h=self.hackathon_id,
            a=avaliador["id"],
        )
        return avaliador

    def homologar_direto(self):
        self.sql(
            "INSERT INTO homologacoes_resultado"
            " (hackathon_id, homologado_por, total_propostas, total_aprovadas)"
            " VALUES (:h, :u, 0, 0)",
            h=self.hackathon_id,
            u=self.lider["id"],
        )

    def emails_de_protocolo(self):
        return self.sql(
            "SELECT * FROM emails_outbox WHERE tipo = 'PROTOCOLO_PROPOSTA'"
            " AND usuario_id = :u ORDER BY criado_em",
            u=self.lider["id"],
        )

    def limpar(self):
        for h in self.hackathons:
            self.sql("DELETE FROM homologacoes_resultado WHERE hackathon_id = :h", h=h)
            self.sql(
                "DELETE FROM avaliacoes WHERE submissao_id IN"
                " (SELECT id FROM submissoes WHERE hackathon_id = :h)",
                h=h,
            )
            self.sql("DELETE FROM designacoes_avaliacao WHERE hackathon_id = :h", h=h)
        super().limpar()


@pytest.fixture
def versoes(sql, usuario_no_banco, novo_email):
    cenario = CenarioVersoes(sql, usuario_no_banco, novo_email)
    try:
        cenario.situacao("HOMOLOGADA")
        sql(
            "UPDATE hackathon SET status = 'ATIVO',"
            " propostas_inicio = now() - interval '1 day',"
            " propostas_fim = now() + interval '1 day' WHERE id = :h",
            h=cenario.hackathon_id,
        )
        cenario.tema_ativo = cenario.novo_tema("Tema da nova versão")
        yield cenario
    finally:
        cenario.limpar()


# --- Reenvio: caminho feliz e histórico ---


def test_reenvio_cria_nova_versao_com_protocolo_proprio_e_preserva_a_anterior(client, versoes):
    original = versoes.enviada(client)
    assert original["versao"] == 1

    resposta = versoes.reenviar(client)

    assert resposta.status_code == 200, resposta.text
    nova = resposta.json()
    assert nova["versao"] == 2
    assert nova["id"] == original["id"]
    assert nova["status"] == "ENVIADA"
    for campo, valor in NOVA_VERSAO.items():
        assert nova[campo] == valor
    assert nova["protocolo"]["numero"] != original["protocolo"]["numero"]
    assert nova["protocolo"]["emitido_em"] == nova["enviado_em"]
    assert nova["enviado_em"] > original["enviado_em"]

    # A consulta e o painel mostram a versão mais recente.
    assert versoes.consultar(client, versoes.integrante()).json() == nova
    painel = client.get(
        f"/equipes/{versoes.equipe_id}/painel", headers=com_token(versoes.lider["id"])
    ).json()
    assert painel["protocolo_proposta"]["numero"] == nova["protocolo"]["numero"]

    historico = versoes.versoes(client).json()
    assert [v["numero"] for v in historico] == [2, 1]
    assert historico[0]["protocolo"]["numero"] == nova["protocolo"]["numero"]
    assert historico[1]["protocolo"]["numero"] == original["protocolo"]["numero"]
    assert historico[1]["titulo"] == original["titulo"]
    assert historico[1]["descricao"] == original["descricao"]
    assert historico[1]["ods"] == original["ods"]
    assert historico[1]["enviada_em"] == original["enviado_em"]
    assert historico[0]["enviada_por"] == str(versoes.lider["id"])


def test_cada_versao_avisa_o_protocolo_por_email(client, versoes):
    versoes.enviada(client)
    nova = versoes.reenviar(client).json()

    chaves = {e["chave_idempotencia"] for e in versoes.emails_de_protocolo()}

    assert len(chaves) == 2
    assert f"protocolo_proposta:{nova['protocolo']['id']}:{versoes.lider['id']}" in chaves


def test_varios_reenvios_numeram_em_sequencia(client, versoes):
    versoes.enviada(client)
    for titulo in ["Segunda", "Terceira"]:
        assert versoes.reenviar(client, titulo=titulo).status_code == 200

    historico = versoes.versoes(client).json()

    assert [(v["numero"], v["titulo"]) for v in historico] == [
        (3, "Terceira"),
        (2, "Segunda"),
        (1, "Coleta seletiva"),
    ]
    assert len({v["protocolo"]["numero"] for v in historico}) == 3


def test_reenvios_simultaneos_nao_repetem_numero_de_versao(client, versoes):
    versoes.enviada(client)
    barreira = Barrier(2)

    def reenviar(titulo):
        barreira.wait(timeout=10)
        return versoes.reenviar(client, titulo=titulo)

    with ThreadPoolExecutor(max_workers=2) as pool:
        respostas = list(pool.map(reenviar, ["A", "B"]))

    assert [r.status_code for r in respostas] == [200, 200]
    assert sorted(r.json()["versao"] for r in respostas) == [2, 3]
    assert [v["numero"] for v in versoes.versoes(client).json()] == [3, 2, 1]


def test_dev_reenvia(client, versoes):
    versoes.enviada(client)
    dev = versoes.usuario_no_banco(papel="DEV", senha=None)
    assert versoes.reenviar(client, quem=dev).status_code == 200


# --- Reenvio: quem pode ---


def test_reenvio_exige_token(client, versoes):
    versoes.enviada(client)
    resposta = client.post(
        versoes.url_reenvio, json={"tema_id": str(versoes.tema_ativo), **NOVA_VERSAO}
    )
    assert resposta.status_code == 401


@pytest.mark.parametrize("vinculo", ["integrante", "externo"])
def test_so_o_lider_reenvia(client, versoes, vinculo):
    versoes.enviada(client)
    quem = versoes.integrante() if vinculo == "integrante" else versoes.usuario_no_banco()

    assert versoes.reenviar(client, quem=quem).status_code == 403
    assert [v["numero"] for v in versoes.versoes(client).json()] == [1]


def test_historico_so_para_integrantes(client, versoes):
    versoes.enviada(client)
    assert versoes.versoes(client, versoes.integrante()).status_code == 200
    assert versoes.versoes(client, versoes.usuario_no_banco()).status_code == 403
    assert client.get(f"{versoes.url_enviada}/versoes").status_code == 401


# --- Reenvio: travas (RN08) ---


def test_rascunho_nao_pode_ser_reenviado(client, versoes):
    versoes.preparar(client)
    assert versoes.reenviar(client).status_code == 409
    assert versoes.versoes(client).status_code == 404


def test_reenvio_depois_do_prazo(client, versoes):
    versoes.enviada(client)
    versoes.prazo(aberto=False)
    assert versoes.reenviar(client).status_code == 409


def test_reenvio_depois_da_distribuicao(client, versoes):
    original = versoes.enviada(client)
    versoes.designar(original["id"])

    resposta = versoes.reenviar(client)

    assert resposta.status_code == 409
    assert "distribuída" in resposta.json()["detail"]
    assert versoes.consultar(client).json() == original


def test_reenvio_com_avaliacao_registrada(client, versoes):
    """Inclui avaliação legada sem designação."""
    original = versoes.enviada(client)
    avaliador = versoes.usuario_no_banco(papel="COMITE_CIENTIFICO", senha=None)
    versoes.sql(
        "INSERT INTO avaliacoes (submissao_id, avaliador_id) VALUES (:s, :a)",
        s=original["id"],
        a=avaliador["id"],
    )

    resposta = versoes.reenviar(client)

    assert resposta.status_code == 409
    assert "avaliação" in resposta.json()["detail"]


def test_reenvio_e_envio_depois_do_resultado_homologado(client, versoes):
    versoes.enviada(client)
    versoes.homologar_direto()

    assert versoes.reenviar(client).status_code == 409


def test_envio_original_depois_do_resultado_homologado(client, versoes):
    versoes.preparar(client)
    versoes.homologar_direto()

    assert versoes.enviar(client).status_code == 409
    assert versoes.linhas()[0]["status"] == "RASCUNHO"


def test_reenvio_de_equipe_nao_homologada(client, versoes):
    versoes.enviada(client)
    versoes.situacao("AGUARDANDO_HOMOLOGACAO")
    assert versoes.reenviar(client).status_code == 409


# --- Reenvio: conteúdo ---


def test_tema_inativo_ou_de_outra_edicao(client, versoes):
    versoes.enviada(client)
    inativo = versoes.novo_tema("Tema desativado", ativo=False)
    assert versoes.reenviar(client, tema_id=str(inativo)).status_code == 409


@pytest.mark.parametrize(
    "campos",
    [
        {"titulo": "   "},
        {"bases_dados": ""},
        {"ods": []},
        {"ods": [18]},
        {"campo_extra": 1},
        {"titulo": None},
    ],
    ids=["titulo-vazio", "bases-vazia", "sem-ods", "ods-18", "extra", "titulo-nulo"],
)
def test_nova_versao_precisa_estar_completa(client, versoes, campos):
    original = versoes.enviada(client)

    resposta = versoes.reenviar(client, **campos)

    assert resposta.status_code == 422
    assert versoes.consultar(client).json() == original
    assert [v["numero"] for v in versoes.versoes(client).json()] == [1]


# --- Dados legados ---


def test_proposta_legada_sem_historico_continua_consultavel(client, versoes):
    """Enviada antes do versionamento e sem protocolo de versão: não se inventa histórico."""
    versoes.preparar(client)
    versoes.sql(
        "UPDATE submissoes SET status = 'ENVIADA', enviado_em = now() WHERE equipe_id = :e",
        e=versoes.equipe_id,
    )
    protocolo = versoes.sql(
        "INSERT INTO protocolos (tipo, equipe_id, submissao_id) VALUES ('PROPOSTA', :e,"
        " (SELECT id FROM submissoes WHERE equipe_id = :e)) RETURNING numero",
        e=versoes.equipe_id,
    )[0]["numero"]

    consulta = versoes.consultar(client)

    assert consulta.status_code == 200
    assert consulta.json()["protocolo"]["numero"] == protocolo
    assert consulta.json()["versao"] is None
    assert versoes.versoes(client).json() == []


# --- Envio x homologação: travas sincronizadas ---


def test_envio_espera_a_homologacao_em_andamento_e_respeita_o_resultado(client, versoes):
    """Com a edição travada pela homologação (FOR UPDATE), o reenvio espera; quando a
    homologação confirma, o reenvio vê o resultado e retorna 409, sem criar versão."""
    versoes.enviada(client)
    travou, liberar = Event(), Event()
    erros: list[BaseException] = []

    async def homologacao():
        conn = await asyncpg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
        )
        try:
            async with conn.transaction():
                await conn.execute(
                    "SELECT 1 FROM hackathon WHERE id = $1 FOR UPDATE", versoes.hackathon_id
                )
                travou.set()
                await asyncio.to_thread(liberar.wait, 15)
                await conn.execute(
                    "INSERT INTO homologacoes_resultado"
                    " (hackathon_id, homologado_por, total_propostas, total_aprovadas)"
                    " VALUES ($1, $2, 1, 0)",
                    versoes.hackathon_id,
                    versoes.lider["id"],
                )
        finally:
            await conn.close()

    def rodar():
        try:
            asyncio.run(homologacao())
        except BaseException as erro:  # noqa: BLE001
            erros.append(erro)
            travou.set()

    fio = Thread(target=rodar)
    fio.start()
    try:
        assert travou.wait(10), "A homologação simulada não travou a edição."
        assert not erros, erros
        with ThreadPoolExecutor(max_workers=1) as pool:
            futuro = pool.submit(versoes.reenviar, client)
            time.sleep(1)
            assert not futuro.done(), "O reenvio não esperou a homologação."
            liberar.set()
            resposta = futuro.result(timeout=15)
    finally:
        liberar.set()
        fio.join(15)

    assert not erros, erros
    assert resposta.status_code == 409
    assert [v["numero"] for v in versoes.versoes(client).json()] == [1]


# --- Homologação do resultado (RF31) ---


@pytest.fixture
def resultado(sql, usuario_no_banco):
    cenario = CenarioResultado(sql, usuario_no_banco)
    try:
        yield cenario
    finally:
        cenario.limpar()


def _codigos(resposta):
    return [p["codigo"] for p in resposta.json()["pendencias"]]


@pytest.mark.parametrize("prazo", ["aberto", "sem-fim"])
def test_nao_homologa_antes_do_fim_do_prazo_de_propostas(client, resultado, prazo):
    resultado.avaliar_tudo()
    if prazo == "aberto":
        resultado.prazo_de_propostas(aberto=True)
    else:
        resultado.sql(
            "UPDATE hackathon SET propostas_fim = NULL WHERE id = :h", h=resultado.hackathon_id
        )

    consulta = resultado.consultar(client)
    homologacao = resultado.homologar(client, [resultado.propostas[0]])

    assert _codigos(consulta) == ["PRAZO_DE_PROPOSTAS_ABERTO"]
    assert consulta.json()["pode_homologar"] is False
    assert homologacao.status_code == 409
    assert resultado.homologacoes() == []


def test_avaliacao_legada_incompleta_impede_homologar(client, resultado):
    """Avaliação migrada como ENVIADA com nota, mas sem rubrica, notas por critério e
    recomendação: não conta como concluída."""
    resultado.avaliar_tudo()
    legado = resultado.propostas[0]
    resultado.sql(
        "DELETE FROM avaliacoes WHERE submissao_id = :s AND avaliador_id = :a",
        s=legado,
        a=resultado.avaliadores[0]["id"],
    )
    resultado.sql(
        "INSERT INTO avaliacoes (submissao_id, avaliador_id, nota, avaliado_em, status)"
        " VALUES (:s, :a, 9, now(), 'ENVIADA')",
        s=legado,
        a=resultado.avaliadores[0]["id"],
    )

    consulta = resultado.consultar(client)

    assert _codigos(consulta) == ["AVALIACAO_INCOMPLETA"]
    assert consulta.json()["pendencias"][0]["submissao_id"] == str(legado)
    assert resultado.homologar(client, [legado]).status_code == 409
    assert resultado.homologacoes() == []


@pytest.mark.parametrize("falta", ["notas-por-criterio", "parecer", "rubrica-de-outra-edicao"])
def test_avaliacao_enviada_sem_tudo_da_rf30_e_incompleta(client, resultado, falta):
    resultado.avaliar_tudo()
    alvo = resultado.propostas[1]
    filtro = "submissao_id = :s AND avaliador_id = :a"
    params = {"s": alvo, "a": resultado.avaliadores[1]["id"]}
    if falta == "notas-por-criterio":
        resultado.sql(
            "DELETE FROM notas_criterio_avaliacao WHERE avaliacao_id ="
            f" (SELECT id FROM avaliacoes WHERE {filtro})",
            **params,
        )
    elif falta == "parecer":
        resultado.sql(f"UPDATE avaliacoes SET comentarios = '  ' WHERE {filtro}", **params)
    else:
        outra = resultado.sql("INSERT INTO hackathon (nome) VALUES ('Outra edição') RETURNING id")[
            0
        ]["id"]
        rubrica = resultado.sql(
            "INSERT INTO rubricas (hackathon_id) VALUES (:h) RETURNING id", h=outra
        )[0]["id"]
        try:
            resultado.sql(
                f"UPDATE avaliacoes SET rubrica_id = :r WHERE {filtro}", r=rubrica, **params
            )
            consulta = resultado.consultar(client)
        finally:
            resultado.sql(
                f"UPDATE avaliacoes SET rubrica_id = :r WHERE {filtro}",
                r=resultado.rubrica_id,
                **params,
            )
            resultado.sql("DELETE FROM rubricas WHERE id = :r", r=rubrica)
            resultado.sql("DELETE FROM hackathon WHERE id = :h", h=outra)
        assert _codigos(consulta) == ["AVALIACAO_INCOMPLETA"]
        return

    assert _codigos(resultado.consultar(client)) == ["AVALIACAO_INCOMPLETA"]


def test_homologa_todas_as_propostas_enviadas(client, resultado):
    """Nenhuma proposta enviada fica de fora do resultado homologado."""
    resultado.avaliar_tudo()

    resposta = resultado.homologar(client, [resultado.propostas[0]])

    assert resposta.status_code == 200, resposta.text
    homologadas = {p["submissao_id"] for p in resposta.json()["propostas"]}
    assert homologadas == {str(p) for p in resultado.propostas}


# --- Migration: propostas já enviadas viram a versão 1 ---


def test_migration_transforma_envios_existentes_na_versao_1():
    """Aplica os SQL reais em schema isolado e desfaz tudo, preservando o banco de testes."""

    async def executar():
        conn = await asyncpg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
        )
        transacao = conn.transaction()
        await transacao.start()
        try:
            schema = f"teste_s509_{uuid4().hex}"
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            pasta = Path(__file__).resolve().parents[1] / "migrations"
            alvo = pasta / "V202611131100__versoes_proposta.sql"
            assert alvo.is_file(), "Monte migrations em /code/migrations para testar os SQL reais."
            for script in sorted(p for p in pasta.glob("V*.sql") if p.name < alvo.name):
                await conn.execute(script.read_text(encoding="utf-8"))

            h = await conn.fetchval("INSERT INTO hackathon (nome) VALUES ('Legado') RETURNING id")
            u = await conn.fetchval(
                "INSERT INTO usuarios (email, papel) VALUES ('lider@legado.com', 'PARTICIPANTE')"
                " RETURNING id"
            )
            t = await conn.fetchval(
                "INSERT INTO temas (hackathon_id, titulo) VALUES ($1, 'Tema') RETURNING id", h
            )

            async def proposta(status, com_protocolo):
                e = await conn.fetchval(
                    "INSERT INTO equipes (hackathon_id) VALUES ($1) RETURNING id", h
                )
                s = await conn.fetchval(
                    "INSERT INTO submissoes (equipe_id, hackathon_id, tema_id, status, titulo,"
                    " descricao, ods, bases_dados, enviado_em) VALUES ($1, $2, $3,"
                    " $4::status_proposta, 'Legado', 'Descrição', '{3,4}', 'IBGE',"
                    " CASE WHEN $4 = 'ENVIADA' THEN now() AT TIME ZONE 'utc' END) RETURNING id",
                    e,
                    h,
                    t,
                    status,
                )
                p = None
                if com_protocolo:
                    p = await conn.fetchval(
                        "INSERT INTO protocolos (tipo, equipe_id, submissao_id, emitido_por)"
                        " VALUES ('PROPOSTA', $1, $2, $3) RETURNING id",
                        e,
                        s,
                        u,
                    )
                return s, p

            enviada, protocolo = await proposta("ENVIADA", True)
            sem_protocolo, _ = await proposta("ENVIADA", False)
            rascunho, _ = await proposta("RASCUNHO", False)

            await conn.execute(alvo.read_text(encoding="utf-8"))

            versoes = await conn.fetch("SELECT * FROM versoes_proposta")
            assert len(versoes) == 1
            versao = versoes[0]
            assert versao["submissao_id"] == enviada
            assert versao["numero"] == 1
            assert versao["protocolo_id"] == protocolo
            assert versao["enviada_por"] == u
            assert versao["titulo"] == "Legado"
            assert versao["ods"] == [3, 4]
            assert versao["enviada_em"] is not None
            for sem_versao in (sem_protocolo, rascunho):
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM versoes_proposta WHERE submissao_id = $1", sem_versao
                    )
                    == 0
                )
            # O protocolo deixa de ser único por proposta: a versão 2 terá o dela.
            await conn.execute(
                "INSERT INTO protocolos (tipo, equipe_id, submissao_id)"
                " SELECT 'PROPOSTA', equipe_id, id FROM submissoes WHERE id = $1",
                enviada,
            )
        finally:
            await transacao.rollback()
            await conn.close()

    asyncio.run(executar())
