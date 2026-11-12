"""BE-S5-05: e-mails gerados pelos eventos do sistema (RF18, RF19, RF22, RF23, RF28, RF33, RF60).

Percorrem os fluxos de verdade pela API e conferem o que ficou na fila. O que importa aqui é
quem é avisado, quando, e que um aviso só existe se a ação foi confirmada.
"""

from datetime import datetime

import pytest

from app.const.config import settings
from app.integrations.email import ProvedorMemoria
from app.services.email_template import data_hora_brasilia
from tests.helpers_email import emails_de
from tests.test_convites import com_token
from tests.test_envio_proposta import CenarioEnvio
from tests.test_inscricao import CenarioInscricao
from tests.test_resultado import CenarioResultado


@pytest.fixture(autouse=True)
def _fila_limpa(fila_vazia):
    yield


@pytest.fixture
def inscricao(sql, usuario_no_banco, novo_email):
    cenario = CenarioInscricao(sql, usuario_no_banco, novo_email)
    yield cenario
    cenario.limpar()


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


@pytest.fixture
def resultado(sql, usuario_no_banco):
    cenario = CenarioResultado(sql, usuario_no_banco)
    cenario.avaliar_tudo()
    try:
        yield cenario
    finally:
        for tabela in ("convites", "protocolos"):
            cenario.sql(
                f"DELETE FROM {tabela} WHERE equipe_id IN"
                " (SELECT id FROM equipes WHERE hackathon_id = :h)",
                h=cenario.hackathon_id,
            )
        cenario.limpar()


def todos_os_emails(sql, tipo: str) -> list[dict]:
    return sql(
        "SELECT * FROM emails_outbox WHERE tipo = CAST(:t AS tipo_email) ORDER BY criado_em, id",
        t=tipo,
    )


def destinatarios(emails: list[dict]) -> list[str]:
    return sorted(e["destinatario_email"] for e in emails)


# --- Convite (RF18, RF19) ---


def test_convite_enfileira_o_aviso_para_quem_tem_conta(client, sql, inscricao):
    convidado = inscricao.usuario_no_banco(senha=None)

    resposta = inscricao.convidar(client, email=convidado["email"].upper(), nome="Maria Souza")

    assert resposta.status_code == 201, resposta.text
    [email] = emails_de(sql, convidado["email"], "CONVITE_EQUIPE")
    assert email["status"] == "PENDENTE"
    assert email["usuario_id"] == convidado["id"]
    assert email["destinatario_email"] == convidado["email"].lower()
    assert email["destinatario_nome"] == "Maria Souza"
    assert email["chave_idempotencia"] == f"convite:{resposta.json()['id']}"
    assert email["assunto"] == "Convite para participar de uma equipe no Hackathon UFPA"
    assert "Olá, Maria Souza." in email["corpo_texto"]
    assert "da equipe Equipe de teste" in email["corpo_texto"]
    assert f"{settings.FRONTEND_URL}/convites" in email["corpo_texto"]


def test_convite_para_quem_ainda_nao_tem_conta_tambem_gera_o_aviso(client, sql, inscricao):
    email_novo = inscricao.novo_email()

    assert inscricao.convidar(client, email=email_novo).status_code == 201

    [email] = emails_de(sql, email_novo, "CONVITE_EQUIPE")
    assert email["usuario_id"] is None


def test_convite_recusado_pelas_regras_nao_gera_aviso(client, sql, inscricao):
    de_fora = inscricao.usuario_no_banco(senha=None)
    existente = inscricao.usuario_no_banco(senha=None)
    inscricao.convidar(client, email=existente["email"])
    nao_lider = inscricao.convidar(client, email=inscricao.novo_email(), quem=de_fora)
    repetido = inscricao.convidar(client, email=existente["email"])
    inscricao.definir_status("INSCRICOES_ENCERRADAS")
    fora_do_prazo = inscricao.convidar(client, email=inscricao.novo_email())

    assert (nao_lider.status_code, repetido.status_code, fora_do_prazo.status_code) == (
        403,
        409,
        409,
    )
    assert len(todos_os_emails(sql, "CONVITE_EQUIPE")) == 1  # só o primeiro convite valeu


def test_convidar_de_novo_depois_de_cancelar_gera_um_aviso_novo(client, sql, inscricao):
    convidado = inscricao.usuario_no_banco(senha=None)
    primeiro = inscricao.convidar(client, email=convidado["email"]).json()["id"]
    cancelar = client.post(
        f"/convites/{primeiro}/cancelar", headers=com_token(inscricao.lider["id"])
    )
    assert cancelar.status_code == 200

    segundo = inscricao.convidar(client, email=convidado["email"]).json()["id"]

    chaves = [e["chave_idempotencia"] for e in emails_de(sql, convidado["email"], "CONVITE_EQUIPE")]
    assert chaves == [f"convite:{primeiro}", f"convite:{segundo}"]


# --- Inscrição concluída e equipe homologada (RF22, RF23, RF60) ---


def test_concluir_a_inscricao_avisa_cada_integrante_com_o_protocolo(client, sql, inscricao):
    pessoas = inscricao.montar(client)

    resposta = inscricao.concluir(client)

    assert resposta.status_code == 200, resposta.text
    protocolo = resposta.json()["protocolo"]
    emails = todos_os_emails(sql, "INSCRICAO_CONCLUIDA")
    protocolo_id = inscricao.protocolos()[0]["id"]
    assert destinatarios(emails) == sorted(p["email"] for p in pessoas)
    for email in emails:
        assert protocolo["numero"] in email["assunto"]
        assert f"Protocolo da inscrição: {protocolo['numero']}" in email["corpo_texto"]
        assert f"{settings.FRONTEND_URL}/equipes/{inscricao.equipe_id}" in email["corpo_texto"]
        assert email["chave_idempotencia"] == f"inscricao:{protocolo_id}:{email['usuario_id']}"
    assert todos_os_emails(sql, "EQUIPE_HOMOLOGADA") == []  # os vínculos ainda não foram aprovados


def test_concluir_ja_homologada_avisa_a_inscricao_e_a_homologacao(client, sql, inscricao):
    pessoas = inscricao.montar(client, vinculos=True)

    assert inscricao.concluir(client).json()["situacao"] == "HOMOLOGADA"

    esperado = sorted(p["email"] for p in pessoas)
    assert destinatarios(todos_os_emails(sql, "INSCRICAO_CONCLUIDA")) == esperado
    assert destinatarios(todos_os_emails(sql, "EQUIPE_HOMOLOGADA")) == esperado


def test_conclusao_recusada_nao_gera_aviso(client, sql, inscricao):
    pessoas = inscricao.montar(client)

    nao_lider = inscricao.concluir(client, quem=pessoas[1])
    sql("DELETE FROM membros_equipe WHERE usuario_id = :u", u=pessoas[2]["id"])
    sem_minimo = inscricao.concluir(client)

    assert (nao_lider.status_code, sem_minimo.status_code) == (403, 409)
    assert todos_os_emails(sql, "INSCRICAO_CONCLUIDA") == []


def test_homologa_so_quando_o_ultimo_comprovante_e_aprovado_e_avisa_uma_unica_vez(
    client, sql, inscricao
):
    pessoas = inscricao.montar(client)
    comprovantes = [inscricao.comprovante(p, "PENDENTE") for p in pessoas]
    organizador = inscricao.usuario_no_banco(papel="ORGANIZADOR", senha=None)
    assert inscricao.concluir(client).json()["situacao"] == "AGUARDANDO_HOMOLOGACAO"

    def aprovar(comprovante):
        resposta = client.post(
            f"/admin/comprovantes/{comprovante}/aprovar", headers=com_token(organizador["id"])
        )
        assert resposta.status_code == 200, resposta.text

    aprovar(comprovantes[0])
    aprovar(comprovantes[1])
    assert todos_os_emails(sql, "EQUIPE_HOMOLOGADA") == []

    aprovar(comprovantes[2])
    emails = todos_os_emails(sql, "EQUIPE_HOMOLOGADA")
    assert destinatarios(emails) == sorted(p["email"] for p in pessoas)
    assert "foi homologada" in emails[0]["corpo_texto"]

    reavaliar = client.post(
        f"/admin/hackathons/{inscricao.hackathon_id}/equipes/reavaliar",
        headers=com_token(organizador["id"]),
    )
    assert reavaliar.status_code == 200
    assert len(todos_os_emails(sql, "EQUIPE_HOMOLOGADA")) == 3  # nada repetido


# --- Protocolo da proposta (RF28) ---


def test_envio_da_proposta_avisa_so_o_lider_com_o_protocolo(client, sql, envio):
    envio.preparar(client)
    integrante = envio.integrante()

    resposta = envio.enviar(client)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    [email] = todos_os_emails(sql, "PROTOCOLO_PROPOSTA")
    assert email["destinatario_email"] == envio.lider["email"]
    assert email["usuario_id"] == envio.lider["id"]
    assert emails_de(sql, integrante["email"]) == []
    numero = corpo["protocolo"]["numero"]
    assert email["assunto"] == f"Proposta enviada: protocolo {numero}"
    assert f"Protocolo da submissão: {numero}" in email["corpo_texto"]
    enviado_em = data_hora_brasilia(datetime.fromisoformat(corpo["enviado_em"]))
    assert f"enviada em {enviado_em} (horário de Brasília)" in email["corpo_texto"]
    assert (
        email["chave_idempotencia"]
        == f"protocolo_proposta:{corpo['protocolo']['id']}:{envio.lider['id']}"
    )


def test_envio_recusado_ou_repetido_nao_gera_aviso_a_mais(client, sql, envio):
    envio.preparar(client)
    envio.situacao("AGUARDANDO_HOMOLOGACAO")
    nao_homologada = envio.enviar(client)
    envio.situacao("HOMOLOGADA")
    assert envio.enviar(client).status_code == 200
    reenvio = envio.enviar(client)

    assert (nao_homologada.status_code, reenvio.status_code) == (409, 409)
    assert len(todos_os_emails(sql, "PROTOCOLO_PROPOSTA")) == 1


def test_aviso_so_vale_se_a_acao_for_confirmada(client, sql, envio, monkeypatch):
    """Se o envio falha depois de enfileirar o aviso, a transação inteira é desfeita: nem a
    proposta nem o e-mail existem, e a nova tentativa funciona."""
    from app.services import submissao
    from app.services.email_eventos import avisar_protocolo_proposta

    envio.preparar(client)

    async def enfileira_e_falha(db, equipe, proposta, protocolo):
        await avisar_protocolo_proposta(db, equipe, proposta, protocolo)
        raise RuntimeError("Falha depois de enfileirar o aviso")

    with monkeypatch.context() as patch:
        patch.setattr(submissao, "avisar_protocolo_proposta", enfileira_e_falha)
        with pytest.raises(RuntimeError, match="Falha depois"):
            envio.enviar(client)

    assert todos_os_emails(sql, "PROTOCOLO_PROPOSTA") == []
    assert envio.protocolos() == []
    assert envio.enviar(client).status_code == 200
    assert len(todos_os_emails(sql, "PROTOCOLO_PROPOSTA")) == 1


# --- Resultado (RF33) ---


def integrantes_das_equipes(resultado: CenarioResultado, usuario_no_banco) -> dict:
    """Líder (já existente) e mais um integrante em cada equipe com proposta."""
    equipes = {}
    for proposta in resultado.propostas:
        equipe_id = resultado.sql("SELECT equipe_id FROM submissoes WHERE id = :s", s=proposta)[0][
            "equipe_id"
        ]
        membro = usuario_no_banco(senha=None)
        resultado.sql(
            "INSERT INTO membros_equipe (equipe_id, usuario_id, hackathon_id, funcao)"
            " VALUES (:e, :u, :h, 'DESENVOLVEDOR')",
            e=equipe_id,
            u=membro["id"],
            h=resultado.hackathon_id,
        )
        pessoas = resultado.sql(
            "SELECT u.email FROM membros_equipe m JOIN usuarios u ON u.id = m.usuario_id"
            " WHERE m.equipe_id = :e",
            e=equipe_id,
        )
        equipes[proposta] = sorted(p["email"] for p in pessoas)
    return equipes


def test_resultado_avisa_todos_os_integrantes_aprovados_ou_nao(
    client, sql, resultado, usuario_no_banco
):
    equipes = integrantes_das_equipes(resultado, usuario_no_banco)
    aprovada, reprovada_1, reprovada_2 = resultado.propostas

    resposta = resultado.homologar(client, [aprovada])

    assert resposta.status_code == 200, resposta.text
    emails = todos_os_emails(sql, "RESULTADO_PROPOSTA")
    assert destinatarios(emails) == sorted(sum(equipes.values(), []))
    assert len(emails) == 6
    por_destinatario = {e["destinatario_email"]: e for e in emails}
    for pessoa in equipes[aprovada]:
        assert "foi aprovada." in por_destinatario[pessoa]["corpo_texto"]
        assert "não foi aprovada" not in por_destinatario[pessoa]["corpo_texto"]
    for pessoa in equipes[reprovada_1] + equipes[reprovada_2]:
        assert "não foi aprovada" in por_destinatario[pessoa]["corpo_texto"]
    for email in emails:
        assert email["assunto"] == "Resultado da sua proposta no Hackathon UFPA"
        assert "/resultado" in email["corpo_texto"]


def test_email_do_resultado_nao_traz_parecer_nem_nota(client, sql, resultado, usuario_no_banco):
    integrantes_das_equipes(resultado, usuario_no_banco)
    sql("UPDATE avaliacoes SET comentarios = 'PARECER-CONFIDENCIAL-XYZ'")

    assert resultado.homologar(client, [resultado.propostas[0]]).status_code == 200

    emails = todos_os_emails(sql, "RESULTADO_PROPOSTA")
    assert emails
    for email in emails:
        conteudo = " ".join([email["assunto"], email["corpo_texto"], email["corpo_html"]])
        assert "PARECER-CONFIDENCIAL-XYZ" not in conteudo
        for nota in ("9,00", "9.00", "7,68", "7.68", "5,00", "5.00"):
            assert nota not in conteudo


def test_homologar_de_novo_ou_sem_permissao_nao_gera_aviso_a_mais(
    client, sql, resultado, usuario_no_banco
):
    integrantes_das_equipes(resultado, usuario_no_banco)
    intruso = usuario_no_banco(papel="PARTICIPANTE", senha=None)
    sem_permissao = resultado.homologar(client, [resultado.propostas[0]], quem=intruso)
    assert resultado.homologar(client, [resultado.propostas[0]]).status_code == 200
    segunda = resultado.homologar(client, [resultado.propostas[0]])

    assert (sem_permissao.status_code, segunda.status_code) == (403, 409)
    assert len(todos_os_emails(sql, "RESULTADO_PROPOSTA")) == 6


# --- A fila entrega o que os eventos geraram ---


def test_o_worker_entrega_os_avisos_do_convite(client, sql, inscricao, processar):
    convidado = inscricao.usuario_no_banco(senha=None)
    inscricao.convidar(client, email=convidado["email"])
    provedor = ProvedorMemoria()

    resumo = processar(provedor)

    assert resumo.enviados == 1
    [mensagem] = provedor.enviadas
    assert mensagem.destinatario == convidado["email"].lower()
    assert "Equipe de teste" in mensagem.texto and "Equipe de teste" in mensagem.html
    [email] = emails_de(sql, convidado["email"], "CONVITE_EQUIPE")
    assert email["status"] == "ENVIADO" and email["corpo_texto"] is None


def test_falha_do_provedor_nao_desfaz_a_acao_principal(client, sql, inscricao, processar):
    from app.integrations.email import ErroEnvioPermanente

    convidado = inscricao.usuario_no_banco(senha=None)
    resposta = inscricao.convidar(client, email=convidado["email"])
    provedor = ProvedorMemoria(falhas=[ErroEnvioPermanente("Destinatário recusado")])

    processar(provedor)

    assert resposta.status_code == 201
    [email] = emails_de(sql, convidado["email"], "CONVITE_EQUIPE")
    assert email["status"] == "FALHA"
    convites = client.get("/convites/meus", headers=com_token(convidado["id"])).json()
    assert [c["id"] for c in convites] == [resposta.json()["id"]]  # o convite continua valendo
