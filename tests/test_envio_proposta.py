"""BE-S4-08: envio transacional, protocolo e consulta da proposta definitiva."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Hackathon
from app.validations.submissao import propostas_abertas
from tests.test_convites import com_token
from tests.test_submissoes import CenarioSubmissoes


class CenarioEnvio(CenarioSubmissoes):
    @property
    def url_enviada(self):
        return f"/equipes/{self.equipe_id}/proposta"

    def enviar(self, client, quem=None):
        return client.post(
            f"{self.url_enviada}/enviar", headers=com_token((quem or self.lider)["id"])
        )

    def consultar(self, client, quem=None):
        return client.get(self.url_enviada, headers=com_token((quem or self.lider)["id"]))

    def situacao(self, valor):
        self.sql(
            "UPDATE equipes SET situacao = CAST(:s AS situacao_equipe) WHERE id = :e",
            s=valor,
            e=self.equipe_id,
        )

    def preparar(self, client, **campos):
        dados = {
            "tema_id": str(self.tema()),
            "titulo": "Coleta seletiva",
            "descricao": "Descrição da solução",
            "ods": [1, 11, 17],
            "bases_dados": "IBGE",
        }
        dados.update(campos)
        resposta = self.requisitar(client, dados=dados)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    def protocolos(self):
        return self.sql("SELECT * FROM protocolos WHERE equipe_id = :e", e=self.equipe_id)

    def limpar(self):
        for h in self.hackathons:
            self.sql(
                "DELETE FROM protocolos WHERE equipe_id IN"
                " (SELECT id FROM equipes WHERE hackathon_id = :h)",
                h=h,
            )
        super().limpar()


@pytest.fixture
def envio(sql, usuario_no_banco, novo_email):
    cenario = CenarioEnvio(sql, usuario_no_banco, novo_email)
    try:
        cenario.situacao("HOMOLOGADA")
        sql(
            "UPDATE hackathon SET status = 'ATIVO',"
            " propostas_inicio = now() - interval '1 day',"
            " propostas_fim = now() + interval '1 day' WHERE id = :h",
            h=cenario.hackathon_id,
        )
        yield cenario
    finally:
        cenario.limpar()


def test_lider_envia_e_integrante_consulta_protocolo_persistido(client, envio):
    rascunho = envio.preparar(client)
    integrante = envio.integrante()
    assert envio.protocolos() == []

    resposta = envio.enviar(client)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["status"] == "ENVIADA"
    assert corpo["documento_url"] is None  # Anexo não é obrigatório.
    assert corpo["enviado_em"] is not None
    for campo in rascunho.keys() - {"status", "enviado_em"}:
        assert corpo[campo] == rascunho[campo]
    protocolo = corpo["protocolo"]
    assert re.fullmatch(r"HK\d{4}-\d{6}", protocolo["numero"])
    assert protocolo["tipo"] == "PROPOSTA"
    assert protocolo["equipe_id"] == str(envio.equipe_id)
    assert protocolo["submissao_id"] == rascunho["id"]
    assert protocolo["emitido_por"] == str(envio.lider["id"])
    assert protocolo["emitido_em"] == corpo["enviado_em"]
    persistido = envio.protocolos()
    assert len(persistido) == 1
    assert str(persistido[0]["id"]) == protocolo["id"]
    assert persistido[0]["numero"] == protocolo["numero"]
    assert persistido[0]["emitido_em"] == envio.linhas()[0]["enviado_em"]
    assert envio.linhas()[0]["status"] == "ENVIADA"
    assert envio.consultar(client, integrante).json() == corpo


@pytest.mark.parametrize("metodo", ["get", "post"])
@pytest.mark.parametrize("vinculo", ["externo", "outra-equipe", "integrante"])
def test_autorizacao_por_vinculo(client, envio, metodo, vinculo):
    envio.preparar(client)
    usuario = envio.integrante() if vinculo == "integrante" else envio.usuario_no_banco(senha=None)
    if vinculo == "outra-equipe":
        envio.criar_equipe(envio.hackathon_id, usuario)
    if metodo == "get":
        assert envio.enviar(client).status_code == 200

    resposta = (
        envio.consultar(client, usuario) if metodo == "get" else envio.enviar(client, usuario)
    )

    assert resposta.status_code == (200 if metodo == "get" and vinculo == "integrante" else 403)
    if resposta.status_code == 403:
        assert "Coleta seletiva" not in resposta.text
        assert "HK20" not in resposta.text
    if metodo == "post":
        assert envio.protocolos() == []


@pytest.mark.parametrize("metodo", ["get", "post"])
@pytest.mark.parametrize("acesso", ["sem-token", "token-invalido", "pendente", "desativado"])
def test_autenticacao_e_conta_ativa(client, envio, metodo, acesso):
    envio.preparar(client)
    if acesso == "sem-token":
        headers = {}
    elif acesso == "token-invalido":
        headers = {"Authorization": "Bearer invalido"}
    else:
        usuario = envio.usuario_no_banco(
            senha=None,
            ativo=acesso != "desativado",
            situacao_conta="PENDENTE" if acesso == "pendente" else "ATIVA",
        )
        headers = com_token(usuario["id"])
    url = envio.url_enviada + ("/enviar" if metodo == "post" else "")

    resposta = getattr(client, metodo)(url, headers=headers)

    assert resposta.status_code == (403 if acesso == "pendente" else 401)
    assert envio.protocolos() == []


@pytest.mark.parametrize("dev", [False, True])
@pytest.mark.parametrize(
    "situacao", ["EM_FORMACAO", "AGUARDANDO_HOMOLOGACAO", "NAO_HOMOLOGADA", "HOMOLOGADA"]
)
def test_apenas_homologada_envia_inclusive_dev(client, envio, situacao, dev):
    envio.preparar(client)
    envio.situacao(situacao)
    usuario = envio.usuario_no_banco(papel="DEV", senha=None) if dev else envio.lider

    resposta = envio.enviar(client, usuario)

    permitido = situacao == "HOMOLOGADA"
    assert resposta.status_code == (200 if permitido else 409), resposta.text
    assert len(envio.protocolos()) == int(permitido)
    assert envio.linhas()[0]["status"] == ("ENVIADA" if permitido else "RASCUNHO")
    if permitido:
        assert resposta.json()["protocolo"]["emitido_por"] == str(usuario["id"])
        assert envio.consultar(client, usuario).status_code == 200


@pytest.mark.parametrize("dev", [False, True])
@pytest.mark.parametrize(
    "inicio,fim,permitido",
    [
        (1, 2, False),
        (-2, -1, False),
        (-1, 1, True),
        (None, None, False),
        (-1, None, False),
        (None, 1, False),
    ],
)
def test_prazo_de_propostas(client, envio, inicio, fim, permitido, dev):
    envio.preparar(client)
    agora = datetime.now(UTC).replace(tzinfo=None)
    envio.sql(
        "UPDATE hackathon SET propostas_inicio = :i, propostas_fim = :f WHERE id = :h",
        i=agora + timedelta(days=inicio) if inicio is not None else None,
        f=agora + timedelta(days=fim) if fim is not None else None,
        h=envio.hackathon_id,
    )
    usuario = envio.usuario_no_banco(papel="DEV", senha=None) if dev else envio.lider

    resposta = envio.enviar(client, usuario)

    assert resposta.status_code == (200 if permitido else 409), resposta.text
    assert len(envio.protocolos()) == int(permitido)


@pytest.mark.parametrize("fuso", [None, UTC, timezone(timedelta(hours=-3))])
@pytest.mark.parametrize(
    "offset,permitido", [(-1, False), (0, True), (1, True), (2, True), (3, False)]
)
def test_prazo_normaliza_fusos_e_inclui_limites(fuso, offset, permitido):
    inicio = datetime(2026, 10, 31, 12, tzinfo=UTC)
    fim = inicio + timedelta(hours=2)
    if fuso is None:
        inicio, fim = inicio.replace(tzinfo=None), fim.replace(tzinfo=None)
    else:
        inicio, fim = inicio.astimezone(fuso), fim.astimezone(fuso)
    hackathon = Hackathon(propostas_inicio=inicio, propostas_fim=fim)
    agora = datetime(2026, 10, 31, 12, tzinfo=UTC) + timedelta(hours=offset)

    assert propostas_abertas(hackathon, agora) is permitido
    assert propostas_abertas(hackathon, agora.replace(tzinfo=None)) is permitido


def test_periodo_invertido_nao_abre_envio():
    agora = datetime.now(UTC)
    hackathon = Hackathon(
        propostas_inicio=agora + timedelta(days=1),
        propostas_fim=agora - timedelta(days=1),
    )
    assert propostas_abertas(hackathon, agora) is False


@pytest.mark.parametrize("dev", [False, True])
@pytest.mark.parametrize("tema", ["inativo", "outra-edicao", "inexistente"])
def test_revalida_tema_no_envio(client, envio, monkeypatch, tema, dev):
    rascunho = envio.preparar(client)
    if tema == "inativo":
        envio.sql("UPDATE temas SET ativo = false WHERE id = :t", t=rascunho["tema_id"])
    else:
        # As FKs já impedem persistir tema inexistente/de outra edição. Simula a leitura
        # para verificar também a defesa no service, sem desabilitar constraints.
        from app.models import Tema

        async def tema_alterado(*args):
            if tema == "inexistente":
                return None
            return Tema(hackathon_id=uuid4(), titulo="Outro", ativo=True)

        monkeypatch.setattr("app.services.submissao.get_tema_by_id", tema_alterado)
    usuario = envio.usuario_no_banco(papel="DEV", senha=None) if dev else envio.lider

    resposta = envio.enviar(client, usuario)

    assert resposta.status_code == (404 if tema == "inexistente" else 409)
    assert envio.linhas()[0]["status"] == "RASCUNHO"
    assert envio.protocolos() == []


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("tema_id", None),
        ("titulo", None),
        ("titulo", ""),
        ("titulo", " \t\n "),
        ("descricao", None),
        ("descricao", ""),
        ("descricao", " \t\n "),
        ("bases_dados", None),
        ("bases_dados", ""),
        ("bases_dados", " \t\n "),
        ("ods", None),
        ("ods", []),
    ],
)
def test_campos_obrigatorios_incompletos_bloqueiam(client, envio, campo, valor):
    envio.preparar(client, **{campo: valor})
    antes = envio.linhas()

    resposta = envio.enviar(client)

    assert resposta.status_code == 422
    assert campo in resposta.json()["detail"]
    assert envio.linhas() == antes
    assert envio.protocolos() == []


@pytest.mark.parametrize("rascunho", [False, True])
def test_get_nao_expoe_rascunho_ou_proposta_ausente(client, envio, rascunho):
    if rascunho:
        envio.preparar(client)
    assert envio.consultar(client).status_code == 404
    if rascunho:
        assert envio.requisitar(client, "get").status_code == 200
    else:
        assert envio.enviar(client).status_code == 404
    assert envio.protocolos() == []


@pytest.mark.parametrize("metodo", ["get", "post"])
def test_equipe_inexistente(client, envio, metodo):
    url = f"/equipes/{uuid4()}/proposta" + ("/enviar" if metodo == "post" else "")
    resposta = getattr(client, metodo)(url, headers=com_token(envio.lider["id"]))
    assert resposta.status_code == 404


def test_reenvio_retorna_409_e_envio_e_imutavel(client, envio):
    envio.preparar(client)
    corpo = envio.enviar(client).json()
    antes = envio.linhas()
    dev = envio.usuario_no_banco(papel="DEV", senha=None)

    for usuario in (envio.lider, dev):
        assert envio.enviar(client, usuario).status_code == 409
        assert envio.requisitar(client, "get", quem=usuario).status_code == 404
        assert (
            envio.requisitar(client, "patch", quem=usuario, dados={"titulo": "Mudou"}).status_code
            == 409
        )
        assert envio.consultar(client, usuario).json() == corpo
    assert envio.linhas() == antes
    assert len(envio.protocolos()) == 1


def test_dois_envios_simultaneos_geram_apenas_um_protocolo(client, envio):
    envio.preparar(client)
    barreira = Barrier(2)

    def enviar():
        barreira.wait(timeout=10)
        return envio.enviar(client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        respostas = list(pool.map(lambda _: enviar(), range(2)))

    assert sorted(r.status_code for r in respostas) == [200, 409]
    assert len(envio.protocolos()) == 1
    assert envio.linhas()[0]["status"] == "ENVIADA"
    sucesso = next(r.json() for r in respostas if r.status_code == 200)
    assert envio.consultar(client).json() == sucesso


def test_envio_trava_equipe_antes_da_proposta(client, envio, monkeypatch):
    from app.controllers.equipe import get_equipe_by_id
    from app.controllers.submissao import get_submissao_da_equipe

    envio.preparar(client)
    bloqueios = []

    async def equipe(db, id_, *, para_atualizar=False):
        assert para_atualizar
        bloqueios.append("equipe")
        return await get_equipe_by_id(db, id_, para_atualizar=para_atualizar)

    async def proposta(db, id_, *, para_atualizar=False):
        assert para_atualizar
        bloqueios.append("proposta")
        return await get_submissao_da_equipe(db, id_, para_atualizar=para_atualizar)

    monkeypatch.setattr("app.services.submissao.get_equipe_by_id", equipe)
    monkeypatch.setattr("app.services.submissao.get_submissao_da_equipe", proposta)

    assert envio.enviar(client).status_code == 200
    assert bloqueios == ["equipe", "proposta"]


@pytest.mark.parametrize("apos_flush", [False, True])
def test_falha_no_protocolo_reverte_envio_e_permite_nova_tentativa(
    client, envio, monkeypatch, apos_flush
):
    from app.controllers.protocolo import criar_protocolo

    envio.preparar(client)
    antes = envio.linhas()

    async def falhar(db, protocolo):
        if apos_flush:
            await criar_protocolo(db, protocolo)
        raise RuntimeError("Falha na emissão do protocolo")

    with monkeypatch.context() as patch:
        patch.setattr("app.services.submissao.criar_protocolo", falhar)
        with pytest.raises(RuntimeError, match="Falha na emissão"):
            envio.enviar(client)

    assert envio.linhas() == antes
    assert envio.protocolos() == []
    assert envio.enviar(client).status_code == 200


def test_banco_impede_segundo_protocolo_por_proposta(client, envio):
    envio.preparar(client)
    enviado = envio.enviar(client).json()

    with pytest.raises(IntegrityError, match="uq_protocolos_proposta_submissao"):
        envio.sql(
            "INSERT INTO protocolos (tipo, equipe_id, submissao_id) VALUES ('PROPOSTA', :e, :s)",
            e=envio.equipe_id,
            s=enviado["id"],
        )
    assert len(envio.protocolos()) == 1


def test_painel_preserva_protocolo_de_inscricao_e_adiciona_o_de_proposta(client, envio):
    inscricao = envio.sql(
        "INSERT INTO protocolos (tipo, equipe_id, emitido_por)"
        " VALUES ('INSCRICAO_EQUIPE', :e, :u) RETURNING *",
        e=envio.equipe_id,
        u=envio.lider["id"],
    )[0]
    painel_url = f"/equipes/{envio.equipe_id}/painel"
    headers = com_token(envio.lider["id"])
    antes = client.get(painel_url, headers=headers).json()
    assert antes["protocolo"]["numero"] == inscricao["numero"]
    assert antes["protocolo_proposta"] is None
    envio.preparar(client)
    enviado = envio.enviar(client).json()

    painel = client.get(painel_url, headers=headers)

    assert painel.status_code == 200
    assert painel.json()["protocolo"] == antes["protocolo"]
    assert painel.json()["protocolo_proposta"] == {
        "numero": enviado["protocolo"]["numero"],
        "emitido_em": enviado["protocolo"]["emitido_em"],
    }
    assert len(envio.protocolos()) == 2
    assert enviado["protocolo"]["numero"] != inscricao["numero"]


def test_swagger_documenta_envio_e_consulta(client):
    documento = client.get("/openapi.json").json()
    for caminho, metodo in [
        ("/equipes/{equipe_id}/proposta/enviar", "post"),
        ("/equipes/{equipe_id}/proposta", "get"),
    ]:
        rota = documento["paths"][caminho][metodo]
        assert rota["tags"] == ["Propostas"]
        assert rota["security"]
        assert {"200", "401", "403", "404", "422"} <= set(rota["responses"])
        if metodo == "post":
            assert "409" in rota["responses"]
            assert "requestBody" not in rota
