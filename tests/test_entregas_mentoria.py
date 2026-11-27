from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import mentoria as service
from tests.test_atribuicoes_mentor import atribuir, headers, s
from tests.test_validacao_submissao_final import REPOSITORIO, criar_pdf

__all__ = ["s"]  # Reutiliza a fixture com equipes homologadas e resultado científico.

AGORA = datetime(2035, 5, 10, 12, tzinfo=UTC)
PRAZO = AGORA + timedelta(days=7)


@pytest.fixture
def mentoria(s, sql, monkeypatch):
    monkeypatch.setattr(service, "agora_utc", lambda: AGORA)
    inicio = (AGORA - timedelta(days=2)).replace(tzinfo=None)
    sql(
        "UPDATE hackathon SET treinamento_concluido_em = :inicio WHERE id = :h",
        inicio=inicio,
        h=s.h,
    )
    try:
        yield s
    finally:
        for tabela in (
            "designacoes_projeto_final",
            "submissoes_finais",
            "entregas_mentoria",
            "marcos_mentoria",
        ):
            sql(f"DELETE FROM {tabela} WHERE hackathon_id = :h", h=s.h)


@pytest.fixture
def lider_da_equipe(mentoria, sql):
    def criar(equipe):
        lider = mentoria.membro(equipe)
        sql(
            "UPDATE membros_equipe SET funcao = 'LIDER' WHERE equipe_id = :e AND usuario_id = :u",
            e=equipe,
            u=lider["id"],
        )
        return lider

    return criar


@pytest.fixture
def marcos(client, mentoria):
    url = f"/admin/hackathons/{mentoria.h}/mentoria/marcos"
    gestor = headers(mentoria.cientifico)

    def cadastrar(*, prazo=PRAZO, ordem=0, tipo="PARCIAL"):
        return client.post(
            url,
            headers=gestor,
            json={
                "titulo": "Protótipo navegável",
                "descricao": "Apresente o fluxo de cadastro.",
                "data_limite": prazo.isoformat(),
                "ordem": ordem,
                "tipo": tipo,
            },
        )

    return cadastrar


def url_entregas(equipe):
    return f"/equipes/{equipe}/mentoria/entregas"


def entregar(client, equipe, autor, marco_id):
    return client.post(
        url_entregas(equipe),
        headers=headers(autor),
        json={
            "marco_id": marco_id,
            "descricao": "Fluxo de cadastro implementado.",
            "referencias": [REPOSITORIO],
        },
    )


def url_submissao_final(equipe):
    return f"/equipes/{equipe}/mentoria/submissao-final"


def submeter(client, equipe, autor, pdf, *, repositorio=REPOSITORIO):
    return client.post(
        url_submissao_final(equipe),
        params={"repositorio_url": repositorio},
        headers=headers(autor) | {"Content-Type": "application/pdf"},
        content=pdf,
    )


def test_gestor_cadastra_pagina_edita_e_exclui_marcos(client, mentoria, marcos):
    prazo_local = PRAZO.astimezone(timezone(timedelta(hours=-3)))
    cadastrados = [marcos(prazo=prazo_local, ordem=ordem) for ordem in (2, 0, 1)]
    assert [resposta.status_code for resposta in cadastrados] == [201, 201, 201]
    segundo, primeiro, intermediario = [resposta.json() for resposta in cadastrados]
    assert primeiro["data_limite"].endswith("Z")
    assert datetime.fromisoformat(primeiro["data_limite"]) == PRAZO

    gestor = headers(mentoria.cientifico)
    lista = f"/admin/hackathons/{mentoria.h}/mentoria/marcos"
    pagina = client.get(lista, headers=gestor, params={"limite": 2, "deslocamento": 1})
    assert pagina.status_code == 200, pagina.text
    assert [item["id"] for item in pagina.json()] == [intermediario["id"], segundo["id"]]

    detalhe = f"{lista}/{primeiro['id']}"
    alterado = client.patch(detalhe, headers=gestor, json={"titulo": "Protótipo revisado"})
    assert alterado.status_code == 200, alterado.text
    consultado = client.get(detalhe, headers=gestor)
    assert consultado.status_code == 200, consultado.text
    assert consultado.json()["titulo"] == "Protótipo revisado"
    assert consultado.json()["data_limite"] == primeiro["data_limite"]
    assert client.delete(detalhe, headers=gestor).status_code == 204
    assert client.get(detalhe, headers=gestor).status_code == 404


def test_calendario_aceita_um_final_depois_dos_parciais(client, mentoria, marcos):
    assert marcos(prazo=AGORA - timedelta(days=3)).status_code == 409
    assert marcos(ordem=1).status_code == 201
    assert marcos(ordem=1, tipo="FINAL").status_code == 409

    final = marcos(ordem=2, tipo="FINAL")
    assert final.status_code == 201, final.text
    assert marcos(ordem=3, tipo="FINAL").status_code == 409
    assert marcos(ordem=2).status_code == 409
    assert marcos(ordem=0).status_code == 201

    url = f"/admin/hackathons/{mentoria.h}/mentoria/marcos/{final.json()['id']}"
    gestor = headers(mentoria.cientifico)
    assert client.patch(url, headers=gestor, json={"ordem": 1}).status_code == 409
    assert client.get(url, headers=gestor).json()["ordem"] == 2


def test_calendario_requer_equipe_aprovada_ou_mentor_vigente(client, mentoria, marcos):
    marco = marcos()
    assert marco.status_code == 201, marco.text
    integrante = mentoria.membro(mentoria.equipes[0])
    reprovado = mentoria.membro(mentoria.equipes[2])
    mentor = mentoria.mentor()
    url = f"/hackathons/{mentoria.h}/mentoria/marcos"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(reprovado)).status_code == 403
    assert client.get(url, headers=headers(mentor)).status_code == 403
    atribuicao = atribuir(client, mentoria, mentor)
    assert atribuicao.status_code == 201, atribuicao.text
    for usuario in (integrante, mentor):
        resposta = client.get(url, headers=headers(usuario))
        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == [marco.json()]


def test_entrega_no_prazo_preserva_historico_apos_prorrogacao(
    client, mentoria, marcos, lider_da_equipe
):
    equipe, outra_equipe, _ = mentoria.equipes
    lider = lider_da_equipe(equipe)
    integrante = mentoria.membro(equipe)
    outro_lider = lider_da_equipe(outra_equipe)
    marco = marcos(prazo=AGORA)
    assert marco.status_code == 201, marco.text
    marco_id = marco.json()["id"]

    assert entregar(client, equipe, integrante, marco_id).status_code == 403
    envio = entregar(client, equipe, lider, marco_id)
    assert envio.status_code == 201, envio.text
    dados = envio.json()
    assert dados["equipe_id"] == str(equipe)
    assert dados["enviado_por"] == str(lider["id"])
    assert dados["referencias"] == [REPOSITORIO]
    assert datetime.fromisoformat(dados["enviado_em"]) == AGORA
    assert dados["data_limite_no_envio"] == marco.json()["data_limite"]
    assert entregar(client, equipe, lider, marco_id).status_code == 409

    admin = f"/admin/hackathons/{mentoria.h}/mentoria/marcos/{marco_id}"
    gestor = headers(mentoria.cientifico)
    antecipado = {"data_limite": (AGORA - timedelta(hours=1)).isoformat()}
    assert client.patch(admin, headers=gestor, json=antecipado).status_code == 409
    assert client.patch(admin, headers=gestor, json={"tipo": "FINAL"}).status_code == 409
    prorrogado = client.patch(admin, headers=gestor, json={"data_limite": PRAZO.isoformat()})
    assert prorrogado.status_code == 200, prorrogado.text
    assert client.delete(admin, headers=gestor).status_code == 409

    segunda = entregar(client, outra_equipe, outro_lider, marco_id)
    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["data_limite_no_envio"] == prorrogado.json()["data_limite"]
    lista = url_entregas(equipe)
    detalhe = f"{lista}/{dados['id']}"
    assert client.get(detalhe, headers=headers(integrante)).json() == dados
    assert client.get(lista, headers=headers(integrante)).json() == [dados]
    assert client.get(detalhe, headers=headers(outro_lider)).status_code == 403
    assert (
        client.get(
            f"{url_entregas(outra_equipe)}/{dados['id']}", headers=headers(outro_lider)
        ).status_code
        == 404
    )


def test_entrega_parcial_recusa_marco_final_prazo_encerrado_e_proposta_reprovada(
    client, mentoria, marcos, lider_da_equipe
):
    equipe, _, reprovada = mentoria.equipes
    lider = lider_da_equipe(equipe)
    lider_reprovado = lider_da_equipe(reprovada)
    vencido = marcos(prazo=AGORA - timedelta(seconds=1))
    parcial = marcos(ordem=0)
    final = marcos(ordem=1, tipo="FINAL")
    assert [resposta.status_code for resposta in (vencido, parcial, final)] == [201, 201, 201]

    assert entregar(client, equipe, lider, str(uuid4())).status_code == 404
    assert entregar(client, equipe, lider, vencido.json()["id"]).status_code == 409
    assert entregar(client, equipe, lider, final.json()["id"]).status_code == 409
    assert entregar(client, reprovada, lider_reprovado, parcial.json()["id"]).status_code == 409
    assert client.get(url_entregas(equipe), headers=headers(lider)).json() == []
    assert client.get(url_entregas(reprovada), headers=headers(lider_reprovado)).json() == []


def test_submissao_final_grava_artefatos_e_permite_download_autorizado(
    client, mentoria, marcos, lider_da_equipe, sql, monkeypatch
):
    equipe = mentoria.equipes[0]
    lider = lider_da_equipe(equipe)
    integrante = mentoria.membro(equipe)
    outro = mentoria.membro(mentoria.equipes[1])
    final = marcos(tipo="FINAL")
    assert final.status_code == 201, final.text
    proposta = sql("SELECT id FROM submissoes WHERE equipe_id = :e", e=equipe)[0]["id"]
    pdf = criar_pdf()
    validar = AsyncMock()
    monkeypatch.setattr(service, "validar_repositorio", validar)
    url = url_submissao_final(equipe)

    assert client.get(url, headers=headers(integrante)).status_code == 404
    assert client.get(f"{url}/relatorio", headers=headers(integrante)).status_code == 404
    assert submeter(client, equipe, integrante, pdf).status_code == 403
    resposta = submeter(client, equipe, lider, pdf, repositorio=f"{REPOSITORIO}.git/")
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["submissao_id"] == str(proposta)
    assert dados["marco_id"] == final.json()["id"]
    assert dados["enviado_por"] == str(lider["id"])
    assert dados["repositorio"] == {"url": REPOSITORIO, "validado_em": dados["enviado_em"]}
    assert dados["relatorio"] == {
        "url": f"{url}/relatorio",
        "tipo": "application/pdf",
        "tamanho_bytes": len(pdf),
    }
    assert submeter(client, equipe, lider, pdf).status_code == 409
    validar.assert_awaited_once_with(REPOSITORIO)

    sql("UPDATE hackathon SET status = 'FINALIZADO' WHERE id = :h", h=mentoria.h)
    leitura = headers(integrante)
    assert client.get(url, headers=leitura).json() == dados
    assert client.get(url, headers=headers(outro)).status_code == 403
    download = client.get(dados["relatorio"]["url"], headers=leitura)
    assert download.status_code == 200, download.text
    assert download.content == pdf
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"] == 'attachment; filename="relatorio-final.pdf"'
    assert download.headers["cache-control"] == "private, no-store"
    assert client.get(dados["relatorio"]["url"], headers=headers(outro)).status_code == 403


def test_falha_na_validacao_do_repositorio_permite_repetir_submissao_final(
    client, mentoria, marcos, lider_da_equipe, monkeypatch
):
    equipe = mentoria.equipes[0]
    lider = lider_da_equipe(equipe)
    pdf = criar_pdf()
    validar = AsyncMock(
        side_effect=[HTTPException(status_code=503, detail="GitHub indisponível"), None]
    )
    monkeypatch.setattr(service, "validar_repositorio", validar)
    assert submeter(client, equipe, lider, pdf).status_code == 404
    assert marcos(tipo="FINAL").status_code == 201
    assert submeter(client, equipe, lider, pdf).status_code == 503
    assert client.get(url_entregas(equipe), headers=headers(lider)).json() == []
    assert submeter(client, equipe, lider, pdf).status_code == 201
    assert validar.await_count == 2


def test_avaliador_acessa_relatorio_validado_enquanto_designacao_esta_vigente(
    client, mentoria, marcos, lider_da_equipe, usuario_no_banco, sql, monkeypatch
):
    equipe = mentoria.equipes[0]
    lider = lider_da_equipe(equipe)
    avaliador = usuario_no_banco(papel="COMITE_TECNICO", senha=None)
    outro_avaliador = usuario_no_banco(papel="COMITE_TECNICO", senha=None)
    proposta = sql("SELECT id FROM submissoes WHERE equipe_id = :e", e=equipe)[0]["id"]
    sql(
        "INSERT INTO designacoes_projeto_final"
        " (submissao_id, equipe_id, hackathon_id, avaliador_id)"
        " VALUES (:p, :e, :h, :a)",
        p=proposta,
        e=equipe,
        h=mentoria.h,
        a=avaliador["id"],
    )
    rota = f"/comite-tecnico/projetos-finais/{proposta}"
    acesso = headers(avaliador)
    caminho_pdf = f"{rota}/relatorio"
    antes = client.get(rota, headers=acesso)
    assert antes.status_code == 200, antes.text
    assert antes.json()["pronto_para_avaliacao"] is False
    assert client.get(caminho_pdf, headers=acesso).status_code == 404

    monkeypatch.setattr(service, "validar_repositorio", AsyncMock())
    assert marcos(tipo="FINAL").status_code == 201
    pdf = criar_pdf()
    envio = submeter(client, equipe, lider, pdf)
    assert envio.status_code == 201, envio.text

    projeto = client.get(rota, headers=acesso)
    assert projeto.status_code == 200, projeto.text
    assert projeto.json()["pronto_para_avaliacao"] is True
    assert projeto.json()["submissao_final"]["relatorio"]["url"] == caminho_pdf
    download = client.get(caminho_pdf, headers=acesso)
    assert download.status_code == 200, download.text
    assert download.content == pdf
    assert client.get(caminho_pdf, headers=headers(outro_avaliador)).status_code == 404

    sql(
        "UPDATE designacoes_projeto_final SET removida_em = now(), removida_por = :gestor"
        " WHERE submissao_id = :p AND avaliador_id = :a",
        gestor=mentoria.organizador["id"],
        p=proposta,
        a=avaliador["id"],
    )
    assert client.get(caminho_pdf, headers=acesso).status_code == 404
