"""BE-S4-07: rascunhos persistidos no PostgreSQL, sem envio definitivo ou avaliação."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from uuid import uuid4

import pytest

from tests.test_convites import Cenario, com_token


class CenarioSubmissoes(Cenario):
    @property
    def url(self):
        return f"/equipes/{self.equipe_id}/proposta/rascunho"

    def requisitar(self, client, metodo="post", *, quem=None, dados=None, equipe_id=None):
        url = f"/equipes/{equipe_id}/proposta/rascunho" if equipe_id else self.url
        kwargs = {"json": dados if dados is not None else {}} if metodo != "get" else {}
        return getattr(client, metodo)(url, headers=com_token((quem or self.lider)["id"]), **kwargs)

    def tema(self, *, hackathon_id=None, ativo=True):
        return self.sql(
            "INSERT INTO temas (hackathon_id, titulo, ativo) VALUES (:h, 'Tema', :a) RETURNING id",
            h=hackathon_id or self.hackathon_id,
            a=ativo,
        )[0]["id"]

    def integrante(self):
        usuario = self.usuario_no_banco(senha=None)
        self.sql(
            "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id, funcao)"
            " VALUES (:e, :u, :h, 'DESENVOLVEDOR')",
            e=self.equipe_id,
            u=usuario["id"],
            h=self.hackathon_id,
        )
        return usuario

    def linhas(self):
        return self.sql("SELECT * FROM submissoes WHERE equipe_id = :e", e=self.equipe_id)

    def marcar_enviada(self):
        tema = self.tema()
        self.sql(
            "UPDATE submissoes SET status = 'ENVIADA', tema_id = :t, titulo = 'Enviada',"
            " descricao = 'Descrição', ods = '{1}', bases_dados = 'IBGE', enviado_em = now()"
            " WHERE equipe_id = :e",
            t=tema,
            e=self.equipe_id,
        )

    def limpar(self):
        for hackathon_id in self.hackathons:
            self.sql("DELETE FROM submissoes WHERE hackathon_id = :h", h=hackathon_id)
            self.sql("DELETE FROM temas WHERE hackathon_id = :h", h=hackathon_id)
        super().limpar()


@pytest.fixture
def propostas(sql, usuario_no_banco, novo_email):
    cenario = CenarioSubmissoes(sql, usuario_no_banco, novo_email)
    try:
        yield cenario
    finally:
        cenario.limpar()


@pytest.mark.parametrize(
    "dados", [{}, {"titulo": "Ideia inicial"}, {"ods": []}, {"descricao": None}]
)
def test_lider_cria_rascunho_incompleto_e_persistido(client, propostas, dados):
    resposta = propostas.requisitar(client, dados=dados)

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["equipe_id"] == str(propostas.equipe_id)
    assert corpo["hackathon_id"] == str(propostas.hackathon_id)
    assert corpo["status"] == "RASCUNHO"
    assert corpo["enviado_em"] is None
    assert corpo["criado_em"] is not None
    assert corpo["atualizado_em"] == corpo["criado_em"]
    linha = propostas.linhas()[0]
    assert str(linha["id"]) == corpo["id"]
    assert linha["status"] == "RASCUNHO"
    assert linha["atualizado_em"] == linha["criado_em"]
    assert linha["enviado_em"] is None
    for campo in ["tema_id", "titulo", "descricao", "ods", "bases_dados", "documento_url"]:
        assert corpo[campo] == dados.get(campo)
        assert linha[campo] == dados.get(campo)
    assert propostas.requisitar(client, "get").json() == corpo


def test_lider_salva_todos_os_campos_com_tema_valido(client, propostas):
    dados = {
        "tema_id": str(propostas.tema()),
        "titulo": "Proposta",
        "descricao": "Descrição",
        "ods": [1, 11, 17],
        "bases_dados": "IBGE",
        "documento_url": "https://exemplo.com/proposta.pdf",
    }

    resposta = propostas.requisitar(client, dados=dados)

    assert resposta.status_code == 201, resposta.text
    for campo, valor in dados.items():
        assert resposta.json()[campo] == valor
        persistido = propostas.linhas()[0][campo]
        assert (str(persistido) if campo == "tema_id" else persistido) == valor


def test_integrante_consulta_conteudo_e_ultimo_salvamento(client, propostas):
    criado = propostas.requisitar(client, dados={"titulo": "Privada"}).json()

    resposta = propostas.requisitar(client, "get", quem=propostas.integrante())

    assert resposta.status_code == 200
    assert resposta.json() == criado
    assert resposta.json()["atualizado_em"] is not None


@pytest.mark.parametrize("metodo", ["post", "get", "patch"])
@pytest.mark.parametrize("vinculo", ["externo", "outra-equipe", "integrante"])
def test_permissoes_por_vinculo(client, propostas, metodo, vinculo):
    criado = propostas.requisitar(client, dados={"titulo": "Privada"}).json()
    if vinculo == "integrante":
        usuario = propostas.integrante()
    else:
        usuario = propostas.usuario_no_banco(senha=None)
        if vinculo == "outra-equipe":
            propostas.criar_equipe(propostas.hackathon_id, usuario)

    resposta = propostas.requisitar(client, metodo, quem=usuario, dados={"titulo": "Alterada"})

    assert resposta.status_code == (200 if vinculo == "integrante" and metodo == "get" else 403)
    assert propostas.requisitar(client, "get").json() == criado
    if resposta.status_code == 403:
        assert criado["id"] not in resposta.text
        assert "Privada" not in resposta.text


@pytest.mark.parametrize("metodo", ["post", "get", "patch"])
@pytest.mark.parametrize("papel", ["COMITE_CIENTIFICO", "COMITE_TECNICO", "MENTOR", "ORGANIZADOR"])
def test_papeis_sem_vinculo_nao_acessam_rascunhos(client, propostas, metodo, papel):
    propostas.requisitar(client)
    usuario = propostas.usuario_no_banco(papel=papel, senha=None)

    resposta = propostas.requisitar(client, metodo, quem=usuario)

    assert resposta.status_code == 403
    assert len(propostas.linhas()) == 1


def test_dev_cria_consulta_e_edita_sem_vinculo(client, propostas):
    dev = propostas.usuario_no_banco(papel="DEV", senha=None)

    criado = propostas.requisitar(client, quem=dev)
    assert criado.status_code == 201
    assert propostas.requisitar(client, "get", quem=dev).json() == criado.json()
    editado = propostas.requisitar(client, "patch", quem=dev, dados={"titulo": "Pelo DEV"})
    assert editado.status_code == 200
    assert editado.json()["titulo"] == "Pelo DEV"
    assert propostas.linhas()[0]["titulo"] == "Pelo DEV"


@pytest.mark.parametrize("metodo", ["post", "get", "patch"])
@pytest.mark.parametrize("acesso", ["sem-token", "token-invalido", "conta-pendente", "desativado"])
def test_autenticacao_e_conta_ativa(client, propostas, metodo, acesso):
    propostas.requisitar(client)
    if acesso == "sem-token":
        headers = {}
    elif acesso == "token-invalido":
        headers = {"Authorization": "Bearer invalido"}
    else:
        usuario = propostas.usuario_no_banco(
            senha=None,
            situacao_conta="PENDENTE" if acesso == "conta-pendente" else "ATIVA",
            ativo=acesso != "desativado",
        )
        headers = com_token(usuario["id"])
    kwargs = {"json": {}} if metodo != "get" else {}

    resposta = getattr(client, metodo)(propostas.url, headers=headers, **kwargs)

    assert resposta.status_code == (403 if acesso == "conta-pendente" else 401)
    assert len(propostas.linhas()) == 1


@pytest.mark.parametrize("metodo", ["post", "get", "patch"])
def test_equipe_inexistente(client, propostas, metodo):
    assert propostas.requisitar(client, metodo, equipe_id=uuid4()).status_code == 404


@pytest.mark.parametrize("metodo", ["get", "patch"])
def test_rascunho_inexistente(client, propostas, metodo):
    resposta = propostas.requisitar(client, metodo)

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Rascunho de proposta não encontrado."}
    assert propostas.linhas() == []


def test_uma_proposta_por_equipe(client, propostas):
    criado = propostas.requisitar(client, dados={"titulo": "Original"}).json()

    resposta = propostas.requisitar(client, dados={"titulo": "Outra"})

    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "Já existe uma proposta para esta equipe."}
    assert propostas.requisitar(client, "get").json() == criado
    assert len(propostas.linhas()) == 1


def test_duas_criacoes_simultaneas_nao_duplicam(client, propostas):
    barreira = Barrier(2)

    def criar():
        barreira.wait(timeout=10)
        return propostas.requisitar(client, dados={"titulo": "Concorrente"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        respostas = list(pool.map(lambda _: criar(), range(2)))

    assert sorted(r.status_code for r in respostas) == [201, 409]
    assert len(propostas.linhas()) == 1
    assert propostas.linhas()[0]["titulo"] == "Concorrente"


def test_constraint_existente_trata_corrida_com_409(client, propostas, monkeypatch):
    propostas.requisitar(client)

    async def sem_proposta(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.submissao.get_submissao_da_equipe", sem_proposta)
    resposta = propostas.requisitar(client)

    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "Já existe uma proposta para esta equipe."}
    assert len(propostas.linhas()) == 1


def test_falha_apos_flush_nao_deixa_rascunho_parcial(client, propostas, monkeypatch):
    from app.controllers.submissao import criar_submissao

    async def falhar(db, proposta):
        await criar_submissao(db, proposta)
        raise RuntimeError("Falha após persistir")

    with monkeypatch.context() as patch:
        patch.setattr("app.services.submissao.criar_submissao", falhar)
        with pytest.raises(RuntimeError, match="Falha após persistir"):
            propostas.requisitar(client)

    assert propostas.linhas() == []
    assert propostas.requisitar(client).status_code == 201


def test_patch_preserva_campos_omitidos_e_atualiza_ultimo_salvamento(client, propostas):
    dados = {
        "tema_id": str(propostas.tema()),
        "titulo": "Original",
        "descricao": "Descrição",
        "ods": [1, 17],
        "bases_dados": "IBGE",
        "documento_url": "https://exemplo.com/a.pdf",
    }
    criado = propostas.requisitar(client, dados=dados).json()

    resposta = propostas.requisitar(client, "patch", dados={"titulo": "Alterado"})

    assert resposta.status_code == 200
    atual = resposta.json()
    assert atual["titulo"] == "Alterado"
    assert datetime.fromisoformat(atual["atualizado_em"]) > datetime.fromisoformat(
        criado["atualizado_em"]
    )
    for campo in criado.keys() - {"titulo", "atualizado_em"}:
        assert atual[campo] == criado[campo]
    assert propostas.requisitar(client, "get").json() == atual
    assert propostas.linhas()[0]["titulo"] == "Alterado"


@pytest.mark.parametrize(
    "campo", ["tema_id", "titulo", "descricao", "ods", "bases_dados", "documento_url"]
)
def test_patch_limpa_campo_opcional_com_null(client, propostas, campo):
    dados = {
        "tema_id": str(propostas.tema()),
        "titulo": "Título",
        "descricao": "Descrição",
        "ods": [11],
        "bases_dados": "IBGE",
        "documento_url": "https://exemplo.com/a.pdf",
    }
    propostas.requisitar(client, dados=dados)

    resposta = propostas.requisitar(client, "patch", dados={campo: None})

    assert resposta.status_code == 200
    assert resposta.json()[campo] is None
    assert propostas.linhas()[0][campo] is None
    for outro in dados.keys() - {campo}:
        assert resposta.json()[outro] == dados[outro]


def test_patch_vazio_registra_salvamento_sem_perder_conteudo(client, propostas):
    criado = propostas.requisitar(client, dados={"titulo": "Original"}).json()

    resposta = propostas.requisitar(client, "patch", dados={})

    assert resposta.status_code == 200
    atual = resposta.json()
    assert atual["titulo"] == "Original"
    assert atual["criado_em"] == criado["criado_em"]
    assert datetime.fromisoformat(atual["atualizado_em"]) > datetime.fromisoformat(
        criado["atualizado_em"]
    )


@pytest.mark.parametrize("metodo", ["post", "patch"])
@pytest.mark.parametrize("tema", ["inexistente", "outro-hackathon", "inativo"])
def test_tema_selecionado_precisa_existir_estar_ativo_e_ser_da_edicao(
    client, propostas, metodo, tema
):
    if metodo == "patch":
        propostas.requisitar(client)
    if tema == "inexistente":
        tema_id = uuid4()
    elif tema == "outro-hackathon":
        tema_id = propostas.tema(hackathon_id=propostas.criar_hackathon())
    else:
        tema_id = propostas.tema(ativo=False)
    antes = propostas.linhas()

    resposta = propostas.requisitar(client, metodo, dados={"tema_id": str(tema_id)})

    assert resposta.status_code == (404 if tema == "inexistente" else 409)
    assert propostas.linhas() == antes


def test_patch_permite_selecionar_outro_tema_valido(client, propostas):
    propostas.requisitar(client)
    tema_id = propostas.tema()

    resposta = propostas.requisitar(client, "patch", dados={"tema_id": str(tema_id)})

    assert resposta.status_code == 200
    assert propostas.linhas()[0]["tema_id"] == tema_id


def test_tema_antigo_inativo_nao_impede_editar_outros_campos_ou_limpar(client, propostas):
    tema_id = propostas.tema()
    propostas.requisitar(client, dados={"tema_id": str(tema_id)})
    propostas.sql("UPDATE temas SET ativo = false WHERE id = :t", t=tema_id)

    editado = propostas.requisitar(client, "patch", dados={"titulo": "Outro campo"})
    assert editado.status_code == 200
    assert editado.json()["tema_id"] == str(tema_id)
    # Selecionar explicitamente o tema inativo continua proibido.
    assert propostas.requisitar(client, "patch", dados={"tema_id": str(tema_id)}).status_code == 409
    limpo = propostas.requisitar(client, "patch", dados={"tema_id": None})
    assert limpo.status_code == 200
    assert limpo.json()["tema_id"] is None


@pytest.mark.parametrize("metodo", ["post", "patch"])
@pytest.mark.parametrize("ods", [[0], [18], [-1], [1, 18], [32768]])
def test_ods_fora_do_intervalo_sao_recusados(client, propostas, metodo, ods):
    if metodo == "patch":
        propostas.requisitar(client, dados={"ods": [1, 17]})
    antes = propostas.linhas()

    resposta = propostas.requisitar(client, metodo, dados={"ods": ods})

    assert resposta.status_code == 422
    assert propostas.linhas() == antes


@pytest.mark.parametrize("metodo", ["post", "patch"])
@pytest.mark.parametrize(
    "campo,valor",
    [
        ("id", str(uuid4())),
        ("usuario_id", str(uuid4())),
        ("equipe_id", str(uuid4())),
        ("hackathon_id", str(uuid4())),
        ("status", "ENVIADA"),
        ("status", "RASCUNHO"),
        ("criado_em", "2026-10-29T00:00:00Z"),
        ("atualizado_em", "2026-10-29T00:00:00Z"),
        ("enviado_em", "2026-10-29T00:00:00Z"),
    ],
)
def test_corpo_rejeita_campos_controlados_pelo_servidor(client, propostas, metodo, campo, valor):
    if metodo == "patch":
        propostas.requisitar(client)
    antes = propostas.linhas()

    resposta = propostas.requisitar(client, metodo, dados={campo: valor})

    assert resposta.status_code == 422
    assert propostas.linhas() == antes


@pytest.mark.parametrize("metodo", ["post", "get", "patch"])
@pytest.mark.parametrize("dev", [False, True])
def test_proposta_enviada_nao_e_rascunho_nem_editavel(client, propostas, metodo, dev):
    propostas.requisitar(client)
    propostas.marcar_enviada()
    antes = propostas.linhas()
    usuario = propostas.usuario_no_banco(papel="DEV", senha=None) if dev else propostas.lider

    resposta = propostas.requisitar(client, metodo, quem=usuario, dados={"titulo": "Alterada"})

    assert resposta.status_code == (404 if metodo == "get" else 409)
    assert propostas.linhas() == antes


@pytest.mark.parametrize("metodo", ["post", "patch"])
@pytest.mark.parametrize("dev", [False, True])
def test_equipe_nao_homologada_fica_em_somente_leitura(client, propostas, metodo, dev):
    if metodo == "patch":
        propostas.requisitar(client, dados={"titulo": "Preservada"})
    propostas.sql(
        "UPDATE equipes SET situacao = 'NAO_HOMOLOGADA' WHERE id = :e", e=propostas.equipe_id
    )
    antes = propostas.linhas()
    usuario = propostas.usuario_no_banco(papel="DEV", senha=None) if dev else propostas.lider

    resposta = propostas.requisitar(client, metodo, quem=usuario, dados={"titulo": "Alterada"})

    assert resposta.status_code == 409
    assert propostas.linhas() == antes
    if metodo == "patch":
        assert propostas.requisitar(client, "get", quem=usuario).status_code == 200
        assert propostas.requisitar(client, "get", quem=propostas.integrante()).status_code == 200


@pytest.mark.parametrize("situacao", ["EM_FORMACAO", "AGUARDANDO_HOMOLOGACAO", "HOMOLOGADA"])
def test_rascunho_nao_exige_homologacao_nem_prazo_de_envio(client, propostas, situacao):
    propostas.sql(
        "UPDATE hackathon SET status = 'ATIVO', inscricoes_fim = now() - interval '2 days',"
        " propostas_inicio = now() - interval '2 days', propostas_fim = now() - interval '1 day'"
        " WHERE id = :h",
        h=propostas.hackathon_id,
    )
    propostas.sql(
        "UPDATE equipes SET situacao = CAST(:s AS situacao_equipe) WHERE id = :e",
        s=situacao,
        e=propostas.equipe_id,
    )

    assert propostas.requisitar(client).status_code == 201
    assert (
        propostas.requisitar(client, "patch", dados={"titulo": "Sem prazo adicional"}).status_code
        == 200
    )


def test_swagger_documenta_contrato_e_nao_expoe_rotas_de_avaliacao(client):
    documento = client.get("/openapi.json").json()
    caminho = "/equipes/{equipe_id}/proposta/rascunho"
    assert set(documento["paths"][caminho]) == {"post", "get", "patch"}
    for metodo in ["post", "get", "patch"]:
        rota = documento["paths"][caminho][metodo]
        assert rota["tags"] == ["Propostas"]
        assert rota["security"]
        assert {"401", "403", "404", "422"} <= set(rota["responses"])
        if metodo != "get":
            assert "409" in rota["responses"]
    for schema in ["SubmissaoCreate", "SubmissaoUpdate"]:
        entrada = documento["components"]["schemas"][schema]
        assert entrada["additionalProperties"] is False
        assert set(entrada["properties"]) == {
            "tema_id",
            "titulo",
            "descricao",
            "ods",
            "bases_dados",
            "documento_url",
        }
    assert not any("avaliac" in p or "submissoes" in p for p in documento["paths"])


def test_salvar_rascunho_nao_cria_avaliacao_ou_protocolo(client, propostas):
    criado = propostas.requisitar(client).json()
    propostas.requisitar(client, "patch", dados={"titulo": "Ainda rascunho"})

    assert propostas.sql("SELECT * FROM avaliacoes WHERE submissao_id = :s", s=criado["id"]) == []
    assert (
        propostas.sql("SELECT * FROM protocolos WHERE equipe_id = :e", e=propostas.equipe_id) == []
    )
    assert propostas.linhas()[0]["status"] == "RASCUNHO"
    assert propostas.linhas()[0]["enviado_em"] is None
