"""BE-S4-10: rubrica, autorização, sigilo, transações e migração de avaliações."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.const.config import settings
from app.models import CriterioRubrica
from app.schemas.avaliacao import NotaCriterio
from app.services.avaliacao import calcular_nota
from tests.test_avaliacao_designacoes import CenarioAvaliacao
from tests.test_convites import com_token


class CenarioCientifico(CenarioAvaliacao):
    def __init__(self, sql, usuario_no_banco):
        super().__init__(sql, usuario_no_banco)
        (self.proposta_id,) = self.pronto(1, 3, 2)
        self.autor = self.avaliadores[0]
        self.designar(self.proposta_id, self.autor)
        self.rubrica_id = sql(
            "INSERT INTO rubricas (hackathon_id) VALUES (:h) RETURNING id", h=self.hackathon_id
        )[0]["id"]
        self.criterios = []
        for ordem, peso, minimo, maximo in [(1, 60, 0, 10), (2, 40, 1, 5)]:
            self.criterios.append(
                sql(
                    "INSERT INTO criterios_rubrica"
                    " (rubrica_id, nome, descricao, peso, escala_min, escala_max, ordem)"
                    " VALUES (:r, :nome, 'Descrição', :p, :mi, :ma, :o) RETURNING id",
                    r=self.rubrica_id,
                    nome=f"Critério {ordem}",
                    p=peso,
                    mi=minimo,
                    ma=maximo,
                    o=ordem,
                )[0]["id"]
            )
        self.publicar()

    def publicar(self):
        self.sql("UPDATE rubricas SET publicada_em = now() WHERE id = :r", r=self.rubrica_id)

    @property
    def url(self):
        return f"/avaliador/propostas/{self.proposta_id}/avaliacao"

    def completo(self):
        return {
            "notas": [
                {"criterio_id": str(c), "nota": n}
                for c, n in zip(self.criterios, ["7.35", "4"], strict=True)
            ],
            "parecer": "A proposta apresenta método consistente e viabilidade demonstrada.",
            "recomendacao": "APROVACAO",
        }

    def salvar(self, client, dados=None, quem=None):
        return client.put(
            f"{self.url}/rascunho",
            json={} if dados is None else dados,
            headers=com_token((quem or self.autor)["id"]),
        )

    def enviar(self, client, dados=None, quem=None):
        return client.post(
            f"{self.url}/enviar", json=dados, headers=com_token((quem or self.autor)["id"])
        )

    def consultar(self, client, quem=None):
        return client.get(self.url, headers=com_token((quem or self.autor)["id"]))

    def registros(self):
        return self.sql("SELECT * FROM avaliacoes WHERE submissao_id = :s", s=self.proposta_id)

    def limpar(self):
        # As notas são excluídas em cascata com suas avaliações.
        self.sql(
            "DELETE FROM protocolos WHERE equipe_id IN"
            " (SELECT id FROM equipes WHERE hackathon_id = :h)",
            h=self.hackathon_id,
        )
        self.sql(
            "DELETE FROM avaliacoes WHERE submissao_id IN"
            " (SELECT id FROM submissoes WHERE hackathon_id = :h)",
            h=self.hackathon_id,
        )
        self.sql("DELETE FROM rubricas WHERE hackathon_id = :h", h=self.hackathon_id)
        super().limpar()


@pytest.fixture
def cientifica(sql, usuario_no_banco):
    cenario = CenarioCientifico(sql, usuario_no_banco)
    try:
        yield cenario
    finally:
        cenario.limpar()


def test_salva_rascunho_incompleto_e_edita_substituindo_conteudo(client, cientifica):
    assert cientifica.consultar(client).status_code == 404
    primeira = cientifica.salvar(client)
    assert primeira.status_code == 200, primeira.text
    assert primeira.json()["status"] == "RASCUNHO"
    assert primeira.json()["nota_final"] is None
    assert primeira.json()["notas"] == []
    assert primeira.json()["avaliado_em"] is None
    dados = cientifica.completo()
    dados["notas"] = dados["notas"][:1]
    editada = cientifica.salvar(client, dados)
    assert editada.status_code == 200
    assert editada.json()["id"] == primeira.json()["id"]
    assert len(editada.json()["notas"]) == 1
    assert editada.json()["atualizado_em"] >= primeira.json()["atualizado_em"]
    assert cientifica.consultar(client).json() == editada.json()
    limpa = cientifica.salvar(client).json()
    assert limpa["notas"] == []
    assert limpa["parecer"] is limpa["recomendacao"] is None
    assert len(cientifica.registros()) == 1


@pytest.mark.parametrize("operacao", ["salvar", "enviar", "consultar"])
def test_nao_designado_recebe_404(client, cientifica, operacao):
    resposta = getattr(cientifica, operacao)(client, quem=cientifica.avaliadores[1])
    assert resposta.status_code == 404
    assert cientifica.registros() == []


@pytest.mark.parametrize("papel", ["PARTICIPANTE", "MENTOR", "COMITE_TECNICO", "ORGANIZADOR"])
def test_perfis_nao_cientificos_nao_avaliam(client, cientifica, papel):
    usuario = cientifica.usuario_no_banco(papel=papel, senha=None)
    cientifica.designar(cientifica.proposta_id, usuario)
    respostas = [
        cientifica.salvar(client, quem=usuario),
        cientifica.enviar(client, cientifica.completo(), quem=usuario),
        cientifica.consultar(client, quem=usuario),
    ]
    assert [r.status_code for r in respostas] == [403, 403, 403]


def test_dev_precisa_de_designacao_e_pode_avaliar_quando_designado(client, cientifica):
    dev = cientifica.usuario_no_banco(papel="DEV", senha=None)
    assert cientifica.salvar(client, quem=dev).status_code == 404
    assert cientifica.enviar(client, cientifica.completo(), quem=dev).status_code == 404
    cientifica.designar(cientifica.proposta_id, dev)
    assert cientifica.salvar(client, quem=dev).status_code == 200
    assert cientifica.enviar(client, cientifica.completo(), quem=dev).status_code == 200


@pytest.mark.parametrize("modo", ["ausente", "rascunho", "outra-edicao"])
def test_exige_rubrica_publicada_da_mesma_edicao(client, cientifica, modo):
    if modo == "outra-edicao":
        # Há rubrica publicada no hackathon original, mas não no da nova proposta.
        outra = CenarioAvaliacao(cientifica.sql, cientifica.usuario_no_banco)
        try:
            cientifica.sql(
                "UPDATE usuarios SET ativo = true WHERE id = :u", u=cientifica.autor["id"]
            )
            proposta = outra.proposta()
            outra.designar(proposta, cientifica.autor)
            url = f"/avaliador/propostas/{proposta}/avaliacao"
            for acao, verbo in [("rascunho", client.put), ("enviar", client.post)]:
                resposta = verbo(
                    f"{url}/{acao}",
                    json=cientifica.completo(),
                    headers=com_token(cientifica.autor["id"]),
                )
                assert resposta.status_code == 409
        finally:
            outra.limpar()
        return
    cientifica.sql("DELETE FROM rubricas WHERE id = :r", r=cientifica.rubrica_id)
    if modo == "rascunho":
        cientifica.sql("INSERT INTO rubricas (hackathon_id) VALUES (:h)", h=cientifica.hackathon_id)
    assert cientifica.salvar(client).status_code == 409
    assert cientifica.enviar(client, cientifica.completo()).status_code == 409
    assert cientifica.registros() == []


def test_proposta_rascunho_nao_pode_ser_avaliada(client, cientifica):
    cientifica.proposta_id = cientifica.proposta("RASCUNHO")
    cientifica.designar(cientifica.proposta_id, cientifica.autor)
    assert cientifica.salvar(client).status_code == 409
    assert cientifica.enviar(client, cientifica.completo()).status_code == 409


@pytest.mark.parametrize(
    "defeito",
    [
        "inexistente",
        "outra-rubrica",
        "abaixo",
        "acima",
        "repetido",
        "nan",
        "infinito",
        "nota-final",
        "avaliador",
        "rubrica",
    ],
)
def test_rejeita_notas_e_campos_invalidos(client, cientifica, defeito):
    dados = cientifica.completo()
    if defeito in {"inexistente", "outra-rubrica"}:
        criterio = uuid4()
        if defeito == "outra-rubrica":
            # Outra rubrica real, sem depender da validação de UUID ou de existência.
            outra = CenarioCientifico(cientifica.sql, cientifica.usuario_no_banco)
            try:
                cientifica.sql(
                    "UPDATE usuarios SET ativo = true WHERE id = :u", u=cientifica.autor["id"]
                )
                dados["notas"][0]["criterio_id"] = str(outra.criterios[0])
                assert cientifica.salvar(client, dados).status_code == 422
                assert cientifica.enviar(client, dados).status_code == 422
            finally:
                outra.limpar()
            return
        dados["notas"][0]["criterio_id"] = str(criterio)
    elif defeito == "repetido":
        dados["notas"].append(dados["notas"][0])
    elif defeito in {"nota-final", "avaliador", "rubrica"}:
        dados[
            {"nota-final": "nota_final", "avaliador": "avaliador_id", "rubrica": "rubrica_id"}[
                defeito
            ]
        ] = "10"
    else:
        dados["notas"][1]["nota"] = {
            "abaixo": "0.99",
            "acima": "5.01",
            "nan": "NaN",
            "infinito": "Infinity",
        }[defeito]
    assert cientifica.salvar(client, dados).status_code == 422
    assert cientifica.enviar(client, dados).status_code == 422
    assert cientifica.registros() == []


@pytest.mark.parametrize(
    "defeito",
    ["criterio", "parecer-ausente", "parecer-vazio", "recomendacao", "recomendacao-invalida"],
)
def test_exige_completude_no_envio_preservando_rascunho(client, cientifica, defeito):
    dados = cientifica.completo()
    if defeito == "criterio":
        dados["notas"].pop()
    elif defeito == "parecer-ausente":
        dados.pop("parecer")
    elif defeito == "parecer-vazio":
        dados["parecer"] = " \n\t "
    elif defeito == "recomendacao":
        dados.pop("recomendacao")
    else:
        dados["recomendacao"] = "TALVEZ"
        assert cientifica.enviar(client, dados).status_code == 422
        return
    assert cientifica.salvar(client, dados).status_code == 200
    antes = cientifica.consultar(client).json()
    assert cientifica.enviar(client).status_code == 422
    assert cientifica.consultar(client).json() == antes


@pytest.mark.parametrize("recomendacao", ["APROVACAO", "REPROVACAO"])
@pytest.mark.parametrize("com_rascunho", [False, True])
def test_envio_calcula_nota_e_registra_data(client, cientifica, com_rascunho, recomendacao):
    dados = cientifica.completo()
    dados["recomendacao"] = recomendacao
    if com_rascunho:
        assert cientifica.salvar(client, dados).status_code == 200
    resposta = cientifica.enviar(client, None if com_rascunho else dados)
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    # 7.35 * 60% + (10 * (4 - 1) / (5 - 1)) * 40% = 7.41
    assert Decimal(corpo["nota_final"]) == Decimal("7.41")
    assert corpo["status"] == "ENVIADA"
    assert corpo["rubrica_id"] == str(cientifica.rubrica_id)
    assert corpo["recomendacao"] == recomendacao
    assert datetime.fromisoformat(corpo["avaliado_em"]) == datetime.fromisoformat(
        corpo["atualizado_em"]
    )
    assert cientifica.consultar(client).json() == corpo
    assert cientifica.registros()[0]["nota"] == Decimal("7.41")


@pytest.mark.parametrize(
    "notas,esperado", [(["0", "1"], "0.00"), (["10", "5"], "10.00"), (["0.125", "1"], "0.08")]
)
def test_normalizacao_limites_e_arredondamento_final(client, cientifica, notas, esperado):
    dados = cientifica.completo()
    for registro, nota in zip(dados["notas"], notas, strict=True):
        registro["nota"] = nota
    resposta = cientifica.enviar(client, dados)
    assert resposta.status_code == 200, resposta.text
    assert Decimal(resposta.json()["nota_final"]) == Decimal(esperado)


def test_calculo_usa_decimal_com_escalas_diferentes():
    criterios = [
        CriterioRubrica(
            id=uuid4(),
            rubrica_id=uuid4(),
            nome="A",
            descricao="A",
            peso=Decimal("33.33"),
            escala_min=2,
            escala_max=8,
            ordem=1,
        ),
        CriterioRubrica(
            id=uuid4(),
            rubrica_id=uuid4(),
            nome="B",
            descricao="B",
            peso=Decimal("66.67"),
            escala_min=0,
            escala_max=100,
            ordem=2,
        ),
    ]
    notas = [
        NotaCriterio(criterio_id=c.id, nota=n)
        for c, n in zip(criterios, [Decimal("5"), Decimal("12.5")], strict=True)
    ]
    resultado = calcular_nota(criterios, notas)
    assert isinstance(resultado, Decimal)
    assert resultado == Decimal("2.50")


def test_avaliacao_enviada_e_imutavel_e_reenvio_da_409(client, cientifica):
    assert cientifica.enviar(client, cientifica.completo()).status_code == 200
    antes = cientifica.consultar(client).json()
    assert cientifica.salvar(client).status_code == 409
    assert cientifica.enviar(client).status_code == 409
    assert cientifica.enviar(client, cientifica.completo()).status_code == 409
    assert cientifica.consultar(client).json() == antes


@pytest.mark.parametrize("com_rascunho", [False, True])
def test_envios_simultaneos_geram_uma_unica_avaliacao(client, cientifica, com_rascunho):
    if com_rascunho:
        assert cientifica.salvar(client, cientifica.completo()).status_code == 200
    barreira = Barrier(2)

    def disparar():
        barreira.wait()
        return cientifica.enviar(client, None if com_rascunho else cientifica.completo())

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(disparar) for _ in range(2)]
        respostas = [f.result() for f in futuros]
    assert sorted(r.status_code for r in respostas) == [200, 409]
    assert len(cientifica.registros()) == 1
    assert len(cientifica.consultar(client).json()["notas"]) == 2


def test_salvamento_simultaneo_ao_envio_nao_altera_avaliacao_final(client, cientifica):
    assert cientifica.salvar(client, cientifica.completo()).status_code == 200
    barreira = Barrier(2)
    rascunho = cientifica.completo()
    rascunho["parecer"] = "Texto do rascunho concorrente."

    def salvar():
        barreira.wait()
        return cientifica.salvar(client, rascunho)

    def enviar():
        barreira.wait()
        return cientifica.enviar(client, cientifica.completo())

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuro_rascunho = pool.submit(salvar)
        futuro_envio = pool.submit(enviar)
        salvo, enviado = futuro_rascunho.result(), futuro_envio.result()
    assert salvo.status_code in (200, 409)
    assert enviado.status_code == 200
    assert cientifica.consultar(client).json() == enviado.json()
    assert len(cientifica.registros()) == 1


@pytest.mark.parametrize("existente", [False, True])
def test_falha_banco_desfaz_avaliacao_e_notas(client, cientifica, monkeypatch, existente):
    import app.services.avaliacao as servico

    antes = None
    if existente:
        assert cientifica.salvar(client, cientifica.completo()).status_code == 200
        antes = cientifica.consultar(client).json()
    substituir_original = servico.substituir_notas

    async def falhar_depois_de_gravar(db, avaliacao_id, notas):
        await substituir_original(db, avaliacao_id, notas)
        await db.exec(text("SELECT 1 / 0"))

    monkeypatch.setattr(servico, "substituir_notas", falhar_depois_de_gravar)
    with pytest.raises(DBAPIError):
        cientifica.enviar(client, cientifica.completo())
    if existente:
        assert cientifica.consultar(client).json() == antes
    else:
        assert cientifica.registros() == []


def test_avaliadores_nao_consultam_nem_alteram_avaliacao_alheia(client, cientifica):
    outra = cientifica.avaliadores[1]
    cientifica.designar(cientifica.proposta_id, outra)
    assert cientifica.enviar(client, cientifica.completo()).status_code == 200
    antes = cientifica.consultar(client).json()
    assert cientifica.consultar(client, quem=outra).status_code == 404
    assert cientifica.salvar(client, quem=outra).status_code == 200
    assert cientifica.consultar(client, quem=outra).json()["parecer"] is None
    assert cientifica.consultar(client).json() == antes


def test_painel_e_proposta_da_equipe_nao_expoem_resultados(client, cientifica):
    assert cientifica.enviar(client, cientifica.completo()).status_code == 200
    equipe = cientifica.sql(
        "SELECT equipe_id FROM submissoes WHERE id = :s", s=cientifica.proposta_id
    )[0]["equipe_id"]
    cientifica.sql(
        "INSERT INTO protocolos (tipo, equipe_id, submissao_id) VALUES ('PROPOSTA', :e, :s)",
        e=equipe,
        s=cientifica.proposta_id,
    )
    lider = cientifica.sql("SELECT usuario_id FROM membros_equipe WHERE equipe_id = :e", e=equipe)[
        0
    ]["usuario_id"]
    for rota in [f"/equipes/{equipe}/painel", f"/equipes/{equipe}/proposta"]:
        resposta = client.get(rota, headers=com_token(lider))
        assert resposta.status_code == 200, resposta.text
        assert cientifica.completo()["parecer"] not in resposta.text

        def conferir(valor):
            if isinstance(valor, dict):
                assert (
                    not {
                        "nota",
                        "notas",
                        "nota_final",
                        "parecer",
                        "comentarios",
                        "recomendacao",
                        "avaliacoes",
                    }
                    & valor.keys()
                )
                for item in valor.values():
                    conferir(item)
            elif isinstance(valor, list):
                for item in valor:
                    conferir(item)

        conferir(resposta.json())


def test_rascunho_iniciado_bloqueia_redistribuicao_e_complemento(client, cientifica):
    assert cientifica.salvar(client).status_code == 200
    antes = cientifica.designacoes(cientifica.proposta_id)
    resposta = cientifica.redistribuir(client, cientifica.proposta_id, cientifica.avaliadores[1:])
    assert resposta.status_code == 409
    assert cientifica.designacoes(cientifica.proposta_id) == antes
    distribuida = cientifica.distribuir(client)
    assert distribuida.status_code == 200
    assert distribuida.json()["designacoes_criadas"] == 0
    assert cientifica.designacoes(cientifica.proposta_id) == antes


def test_redistribuicao_concorrente_revoga_acesso_antes_de_salvar(client, cientifica, monkeypatch):
    import app.services.avaliacao as servico

    aguardando = Event()
    continuar = Event()
    bloquear_original = servico.get_hackathon_para_atualizar

    async def esperar_antes_do_lock(db, hackathon_id):
        aguardando.set()
        assert await asyncio.to_thread(continuar.wait, 10), "Redistribuição não terminou."
        return await bloquear_original(db, hackathon_id)

    monkeypatch.setattr(servico, "get_hackathon_para_atualizar", esperar_antes_do_lock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        futuro = pool.submit(cientifica.salvar, client, cientifica.completo())
        try:
            assert aguardando.wait(10), "Salvamento não chegou ao bloqueio."
            resposta = cientifica.redistribuir(
                client, cientifica.proposta_id, cientifica.avaliadores[1:]
            )
            assert resposta.status_code == 200, resposta.text
        finally:
            continuar.set()
        assert futuro.result().status_code == 404
    assert cientifica.registros() == []
    assert cientifica.autor["id"] not in cientifica.avaliadores_da(cientifica.proposta_id)


def test_unicidade_no_banco(client, cientifica):
    assert cientifica.salvar(client, cientifica.completo()).status_code == 200
    with pytest.raises(IntegrityError):
        cientifica.sql(
            "INSERT INTO avaliacoes (submissao_id, avaliador_id) VALUES (:s, :a)",
            s=cientifica.proposta_id,
            a=cientifica.autor["id"],
        )
    with pytest.raises(IntegrityError):
        cientifica.sql(
            "INSERT INTO notas_criterio_avaliacao (avaliacao_id, criterio_id, nota)"
            " VALUES (:a, :c, 1)",
            a=cientifica.registros()[0]["id"],
            c=cientifica.criterios[0],
        )


@pytest.mark.parametrize("legado", [False, True, "duplicado"])
def test_migration_em_banco_vazio_e_atualizado(legado):
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
            schema = f"teste_s410_{uuid4().hex}"
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            pasta = Path(__file__).resolve().parents[1] / "migrations"
            alvo = pasta / "V202611031800__avaliacao_cientifica.sql"
            assert alvo.is_file(), "Monte migrations em /code/migrations para testar os SQL reais."
            for script in sorted(p for p in pasta.glob("V*.sql") if p.name < alvo.name):
                await conn.execute(script.read_text(encoding="utf-8"))
            registros = []
            if legado:
                h = await conn.fetchval(
                    "INSERT INTO hackathon (nome) VALUES ('Legado') RETURNING id"
                )
                e = await conn.fetchval(
                    "INSERT INTO equipes (hackathon_id) VALUES ($1) RETURNING id", h
                )
                s = await conn.fetchval(
                    "INSERT INTO submissoes (equipe_id, hackathon_id) VALUES ($1, $2) RETURNING id",
                    e,
                    h,
                )
                u = await conn.fetchval(
                    "INSERT INTO usuarios (email, papel)"
                    " VALUES ('legado@testes.com', 'COMITE_CIENTIFICO') RETURNING id"
                )
                exemplos = [(Decimal("8.765"), datetime(2026, 11, 1)), (None, None)]
                if legado != "duplicado":
                    exemplos += [(None, datetime(2026, 11, 2)), (Decimal("0"), None)]
                for indice, (nota, data) in enumerate(exemplos):
                    if registros and legado != "duplicado":
                        u = await conn.fetchval(
                            "INSERT INTO usuarios (email, papel)"
                            " VALUES ($1, 'COMITE_CIENTIFICO') RETURNING id",
                            f"outro{indice}@testes.com",
                        )
                    registros.append(
                        await conn.fetchrow(
                            "INSERT INTO avaliacoes (submissao_id, avaliador_id, nota, comentarios,"
                            " avaliado_em) VALUES ($1, $2, $3, 'Preservar', $4) RETURNING *",
                            s,
                            u,
                            nota,
                            data,
                        )
                    )
            if legado == "duplicado":
                with pytest.raises(asyncpg.RaiseError, match="avaliacoes_duplicadas"):
                    await conn.execute(alvo.read_text(encoding="utf-8"))
                return
            await conn.execute(alvo.read_text(encoding="utf-8"))
            assert await conn.fetchval("SELECT count(*) FROM notas_criterio_avaliacao") == 0
            for antigo in registros:
                novo = await conn.fetchrow("SELECT * FROM avaliacoes WHERE id = $1", antigo["id"])
                for chave in antigo.keys():
                    assert novo[chave] == antigo[chave]
                finalizada = antigo["nota"] is not None or antigo["avaliado_em"] is not None
                assert novo["status"] == ("ENVIADA" if finalizada else "RASCUNHO")
                assert novo["rubrica_id"] is novo["recomendacao"] is None
                assert novo["atualizado_em"] is not None
        finally:
            await transacao.rollback()
            await conn.close()

    asyncio.run(executar())
