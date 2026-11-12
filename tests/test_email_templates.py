"""BE-S5-05: templates dos e-mails transacionais (RNF28, RF60). Não usam o banco."""

from datetime import UTC, datetime

import pytest

from app.const.enums import TipoEmail
from app.services.email_template import (
    CONTEXTO_OBRIGATORIO,
    DIRETORIO_TEMPLATES,
    data_hora_brasilia,
    renderizar,
)

LINK = "https://hackathon.example/entrar?x=1&y=2"

VALORES = {
    "nome": "Maria Souza",
    "link": LINK,
    "validade_minutos": 30,
    "perfil": "Mentor",
    "equipe_nome": "Equipe Açaí",
    "lider_nome": "João Lima",
    "protocolo_numero": "HK2026-000123",
    "enviado_em": datetime(2026, 11, 12, 15, 30, tzinfo=UTC),
    "aprovada": True,
}


def contexto(tipo: TipoEmail, **alterados) -> dict:
    return {**{c: VALORES[c] for c in CONTEXTO_OBRIGATORIO[tipo]}, **alterados}


def test_todo_tipo_tem_template_de_texto_e_html():
    for tipo in TipoEmail:
        for extensao in ("txt", "html"):
            assert (DIRETORIO_TEMPLATES / f"{tipo.value.lower()}.{extensao}").is_file(), tipo


@pytest.mark.parametrize("tipo", list(TipoEmail))
def test_renderiza_assunto_texto_e_html_com_o_link(tipo):
    email = renderizar(tipo, contexto(tipo))

    assert email.assunto and "\n" not in email.assunto
    assert "Maria Souza" in email.texto
    assert "Maria Souza" in email.html
    assert LINK in email.texto
    # No HTML o "&" do link vira entidade; o link aparece no botão e no texto de apoio
    assert email.html.count("https://hackathon.example/entrar?x=1&amp;y=2") == 2
    assert 'lang="pt-BR"' in email.html


@pytest.mark.parametrize("tipo", list(TipoEmail))
def test_falta_de_valor_no_contexto_e_erro_e_nao_e_mail_incompleto(tipo):
    for faltando in CONTEXTO_OBRIGATORIO[tipo]:
        incompleto = contexto(tipo)
        del incompleto[faltando]
        with pytest.raises(ValueError, match=faltando):
            renderizar(tipo, incompleto)


def test_assuntos_com_protocolo_trazem_o_numero():
    for tipo in (TipoEmail.INSCRICAO_CONCLUIDA, TipoEmail.PROTOCOLO_PROPOSTA):
        assert "HK2026-000123" in renderizar(tipo, contexto(tipo)).assunto


def test_html_escapa_valores_e_o_texto_simples_nao():
    nome = '<script>alert("x")</script>'
    email = renderizar(TipoEmail.CONVITE_EQUIPE, contexto(TipoEmail.CONVITE_EQUIPE, nome=nome))

    assert "<script>" not in email.html
    assert "&lt;script&gt;" in email.html
    assert nome in email.texto


def test_assunto_continua_em_uma_linha_mesmo_com_quebra_no_valor():
    email = renderizar(
        TipoEmail.PROTOCOLO_PROPOSTA,
        contexto(TipoEmail.PROTOCOLO_PROPOSTA, protocolo_numero="HK1\r\nBcc: alguem@x.com"),
    )

    assert "\n" not in email.assunto and "\r" not in email.assunto


def test_sem_link_o_email_sai_sem_botao():
    email = renderizar(
        TipoEmail.EQUIPE_HOMOLOGADA, contexto(TipoEmail.EQUIPE_HOMOLOGADA, link=None)
    )

    assert "<a href" not in email.html
    assert "http" not in email.texto


def test_convite_sem_nome_de_equipe_ou_de_lider_usa_texto_generico():
    email = renderizar(
        TipoEmail.CONVITE_EQUIPE,
        contexto(TipoEmail.CONVITE_EQUIPE, equipe_nome=None, lider_nome=None),
    )

    assert "O líder da equipe convidou você para participar de uma equipe" in email.texto


@pytest.mark.parametrize(
    ("aprovada", "esperado", "ausente"),
    [
        (True, "Açaí foi aprovada.", "não foi aprovada"),
        (False, "Açaí não foi aprovada.", "Açaí foi"),
    ],
)
def test_resultado_diz_so_se_a_proposta_foi_aprovada(aprovada, esperado, ausente):
    email = renderizar(
        TipoEmail.RESULTADO_PROPOSTA, contexto(TipoEmail.RESULTADO_PROPOSTA, aprovada=aprovada)
    )

    assert esperado in email.texto
    assert ausente not in email.texto


def test_resultado_nunca_expoe_parecer_nem_nota_mesmo_que_venham_no_contexto():
    email = renderizar(
        TipoEmail.RESULTADO_PROPOSTA,
        contexto(
            TipoEmail.RESULTADO_PROPOSTA, parecer="PARECER-SECRETO", nota="9,75", senha="S3NHA"
        ),
    )

    for conteudo in (email.assunto, email.texto, email.html):
        assert "PARECER-SECRETO" not in conteudo
        assert "9,75" not in conteudo
        assert "S3NHA" not in conteudo


@pytest.mark.parametrize(
    ("momento", "esperado"),
    [
        (datetime(2026, 11, 12, 15, 30), "12/11/2026 às 12:30"),  # sem fuso: vale UTC
        (datetime(2026, 11, 12, 15, 30, tzinfo=UTC), "12/11/2026 às 12:30"),
        (datetime(2026, 11, 12, 2, 5, tzinfo=UTC), "11/11/2026 às 23:05"),  # volta um dia
    ],
)
def test_data_e_hora_saem_no_horario_de_brasilia(momento, esperado):
    assert data_hora_brasilia(momento) == esperado


def test_protocolo_da_proposta_mostra_o_horario_de_brasilia():
    email = renderizar(TipoEmail.PROTOCOLO_PROPOSTA, contexto(TipoEmail.PROTOCOLO_PROPOSTA))

    assert "12/11/2026 às 12:30" in email.texto
    assert "horário de Brasília" in email.texto


def test_confirmacao_e_recuperacao_orientam_quem_nao_fez_o_pedido():
    confirmacao = renderizar(TipoEmail.CONFIRMACAO_EMAIL, contexto(TipoEmail.CONFIRMACAO_EMAIL))
    recuperacao = renderizar(TipoEmail.RECUPERACAO_SENHA, contexto(TipoEmail.RECUPERACAO_SENHA))

    assert "ignore esta mensagem" in confirmacao.texto
    assert "30 minutos" in recuperacao.texto
    assert "a sua senha continua a mesma" in recuperacao.texto
