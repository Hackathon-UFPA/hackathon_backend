"""Requisitos e transições da homologação com leituras do banco simuladas."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import (
    FuncaoMembro,
    PapelUsuario,
    SituacaoEquipe,
    StatusComprovante,
    StatusConvite,
    StatusHackathon,
    TipoIntegrante,
    TipoTermo,
)
from app.const.inscricao import CodigoPendencia
from app.models import ComprovanteVinculo, Convite, Equipe, Hackathon, MembroEquipe, Termo, Usuario
from app.services import homologacao

pytestmark = pytest.mark.unit

AGORA = datetime(2026, 11, 7, 12, tzinfo=UTC)


@pytest.fixture
def cenario(monkeypatch):
    hackathon = Hackathon()
    equipe = Equipe(hackathon_id=hackathon.id)
    usuarios = [
        Usuario(email=f"pessoa{i}@example.com", papel=PapelUsuario.PARTICIPANTE) for i in range(3)
    ]
    membros = [
        MembroEquipe(
            equipe_id=equipe.id,
            hackathon_id=hackathon.id,
            usuario_id=usuario.id,
            funcao=FuncaoMembro.LIDER if i == 0 else FuncaoMembro.DESENVOLVEDOR,
        )
        for i, usuario in enumerate(usuarios)
    ]
    termos = [
        Termo(hackathon_id=hackathon.id, tipo=tipo, versao="1", titulo=tipo, conteudo="Texto")
        for tipo in TipoTermo
    ]
    comprovantes = {
        usuario.id: ComprovanteVinculo(
            usuario_id=usuario.id,
            hackathon_id=hackathon.id,
            arquivo_url="https://example.com/comprovante.pdf",
            status=StatusComprovante.APROVADO,
        )
        for usuario in usuarios
    }
    colaboradores = {
        "listar_membros_com_usuario": AsyncMock(
            return_value=list(reversed(list(zip(membros, usuarios, strict=True))))
        ),
        "listar_termos_vigentes": AsyncMock(return_value=termos),
        "listar_aceites_dos_usuarios": AsyncMock(
            return_value={usuario.id: {termo.id for termo in termos} for usuario in usuarios}
        ),
        "listar_usuarios_com_convite_aceito": AsyncMock(
            return_value={usuario.id for usuario in usuarios[1:]}
        ),
        "ultimo_comprovante_por_usuario": AsyncMock(return_value=comprovantes),
        "ultima_autodeclaracao_por_usuario": AsyncMock(return_value={}),
        "listar_convites_da_equipe": AsyncMock(return_value=[]),
        "avisar_equipe_homologada": AsyncMock(),
        "notificar_equipe_homologada": AsyncMock(),
    }
    for nome, substituto in colaboradores.items():
        monkeypatch.setattr(homologacao, nome, substituto)
    return SimpleNamespace(
        db=MagicMock(spec=AsyncSession),
        equipe=equipe,
        hackathon=hackathon,
        usuarios=usuarios,
        membros=membros,
        **colaboradores,
    )


def avaliar(cenario):
    return asyncio.run(
        homologacao.avaliar(cenario.db, cenario.equipe, cenario.hackathon, agora=AGORA)
    )


def test_equipe_completa_e_homologavel_e_mostra_lider_primeiro_sem_gravar(cenario):
    resultado = avaliar(cenario)

    assert resultado.total == 3
    assert resultado.pode_concluir is True
    assert resultado.homologavel is True
    assert resultado.pendencias == []
    assert resultado.integrantes[0].usuario is cenario.usuarios[0]
    assert resultado.integrantes[0].convite is None
    cenario.db.add.assert_not_called()
    cenario.db.flush.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "status, codigo",
    [
        (None, CodigoPendencia.COMPROVANTE_NAO_ENVIADO),
        (StatusComprovante.PENDENTE, CodigoPendencia.COMPROVANTE_PENDENTE),
        (StatusComprovante.RECUSADO, CodigoPendencia.COMPROVANTE_RECUSADO),
    ],
)
def test_comprovante_pendente_bloqueia_homologacao_mas_permite_conclusao(cenario, status, codigo):
    usuario_id = cenario.usuarios[1].id
    comprovantes = cenario.ultimo_comprovante_por_usuario.return_value
    if status is None:
        comprovantes.pop(usuario_id)
    else:
        comprovantes[usuario_id].status = status

    resultado = avaliar(cenario)

    assert resultado.pode_concluir is True
    assert resultado.homologavel is False
    assert [(p.codigo, p.usuario_id, p.bloqueia_conclusao) for p in resultado.pendencias] == [
        (codigo, usuario_id, False)
    ]


@pytest.mark.parametrize("comprovante_exigido", [False, True])
def test_comprovante_profissional_segue_a_politica_da_edicao(cenario, comprovante_exigido):
    cenario.equipe.categoria = "MISTA"
    cenario.hackathon.exige_comprovante_profissional = comprovante_exigido
    membro = cenario.membros[1]
    membro.tipo_integrante = TipoIntegrante.PROFISSIONAL
    cenario.ultimo_comprovante_por_usuario.return_value.pop(membro.usuario_id)

    resultado = avaliar(cenario)

    assert resultado.pode_concluir is True
    assert resultado.homologavel is (not comprovante_exigido)
    _, _, _, tipos = cenario.ultimo_comprovante_por_usuario.await_args.args
    assert tipos[membro.usuario_id] == TipoIntegrante.PROFISSIONAL
    if comprovante_exigido:
        (pendencia,) = resultado.pendencias
        assert pendencia.codigo == CodigoPendencia.COMPROVANTE_NAO_ENVIADO
        assert pendencia.usuario_id == membro.usuario_id
        assert "profissional" in pendencia.mensagem


@pytest.mark.parametrize(
    "defeito, codigo",
    [
        ("conta-desativada", CodigoPendencia.CONTA_DESATIVADA),
        ("convite-ausente", CodigoPendencia.CONVITE_NAO_ACEITO),
        ("termo-ausente", CodigoPendencia.TERMOS_NAO_ACEITOS),
    ],
)
def test_requisito_do_integrante_bloqueia_conclusao(cenario, defeito, codigo):
    usuario = cenario.usuarios[1]
    if defeito == "conta-desativada":
        usuario.ativo = False
    elif defeito == "convite-ausente":
        cenario.listar_usuarios_com_convite_aceito.return_value.remove(usuario.id)
    else:
        cenario.listar_aceites_dos_usuarios.return_value[usuario.id].pop()

    resultado = avaliar(cenario)

    assert resultado.pode_concluir is False
    assert resultado.homologavel is False
    assert [(p.codigo, p.usuario_id, p.bloqueia_conclusao) for p in resultado.pendencias] == [
        (codigo, usuario.id, True)
    ]


@pytest.mark.parametrize("quantidade", [0, 1])
def test_exige_publicacao_dos_dois_tipos_de_termo(cenario, quantidade):
    cenario.listar_termos_vigentes.return_value = cenario.listar_termos_vigentes.return_value[
        :quantidade
    ]

    resultado = avaliar(cenario)

    assert resultado.pode_concluir is False
    assert [p.codigo for p in resultado.pendencias] == [CodigoPendencia.TERMOS_NAO_PUBLICADOS]


@pytest.mark.parametrize(
    "minimo, maximo, codigo",
    [
        (4, 5, CodigoPendencia.EQUIPE_ABAIXO_DO_MINIMO),
        (1, 2, CodigoPendencia.EQUIPE_ACIMA_DO_MAXIMO),
    ],
)
def test_tamanho_da_equipe_respeita_limites_do_hackathon(cenario, minimo, maximo, codigo):
    cenario.hackathon.min_integrantes = minimo
    cenario.hackathon.max_integrantes = maximo

    resultado = avaliar(cenario)

    assert resultado.pode_concluir is False
    assert [p.codigo for p in resultado.pendencias] == [codigo]


@pytest.mark.parametrize(
    "situacao",
    [SituacaoEquipe.EM_FORMACAO, SituacaoEquipe.AGUARDANDO_HOMOLOGACAO, SituacaoEquipe.HOMOLOGADA],
)
def test_prazo_encerrado_bloqueia_somente_equipe_em_formacao(cenario, situacao):
    cenario.equipe.situacao = situacao
    cenario.hackathon.status = StatusHackathon.INSCRICOES_ENCERRADAS

    resultado = avaliar(cenario)

    assert resultado.inscricoes_abertas is False
    assert resultado.pode_concluir is (situacao != SituacaoEquipe.EM_FORMACAO)
    assert [p.codigo for p in resultado.pendencias] == (
        [CodigoPendencia.INSCRICOES_ENCERRADAS] if situacao == SituacaoEquipe.EM_FORMACAO else []
    )


@pytest.mark.parametrize("status", list(StatusConvite))
def test_painel_considera_apenas_convite_mais_recente_por_email(cenario, status):
    antigo = Convite(
        equipe_id=cenario.equipe.id,
        nome="Convidado",
        email="PESSOA@example.com",
        convidado_por=cenario.usuarios[0].id,
        enviado_em=(AGORA - timedelta(days=1)).replace(tzinfo=None),
    )
    recente = Convite(
        equipe_id=cenario.equipe.id,
        nome="Convidado",
        email="pessoa@example.com",
        convidado_por=cenario.usuarios[0].id,
        enviado_em=AGORA,
        status=status,
    )
    cenario.listar_convites_da_equipe.return_value = [recente, antigo]

    resultado = avaliar(cenario)

    esperado = [recente] if status in {StatusConvite.PENDENTE, StatusConvite.RECUSADO} else []
    assert resultado.convites_em_aberto == esperado


@pytest.mark.parametrize("situacao", list(SituacaoEquipe))
@pytest.mark.parametrize("homologavel", [False, True])
def test_reavaliacao_aplica_transicoes_e_preserva_estados_nao_elegiveis(
    cenario, monkeypatch, situacao, homologavel
):
    cenario.equipe.situacao = situacao
    cenario.equipe.homologada_em = AGORA if situacao == SituacaoEquipe.HOMOLOGADA else None
    avaliacao = AsyncMock(return_value=SimpleNamespace(homologavel=homologavel))
    monkeypatch.setattr(homologacao, "avaliar", avaliacao)
    relogio = Mock(wraps=datetime)
    relogio.now.return_value = AGORA
    monkeypatch.setattr(homologacao, "datetime", relogio)
    antes = cenario.equipe.model_dump()
    elegivel = situacao in {SituacaoEquipe.AGUARDANDO_HOMOLOGACAO, SituacaoEquipe.HOMOLOGADA}
    esperado = (
        (SituacaoEquipe.HOMOLOGADA if homologavel else SituacaoEquipe.AGUARDANDO_HOMOLOGACAO)
        if elegivel
        else situacao
    )

    resultado = asyncio.run(
        homologacao.reavaliar_homologacao(cenario.db, cenario.equipe, cenario.hackathon)
    )

    assert resultado == cenario.equipe.situacao == esperado
    if elegivel:
        avaliacao.assert_awaited_once_with(cenario.db, cenario.equipe, cenario.hackathon)
    else:
        avaliacao.assert_not_awaited()
    if esperado != situacao:
        assert cenario.equipe.atualizado_em == AGORA
        assert cenario.equipe.homologada_em == (AGORA if homologavel else None)
        cenario.db.add.assert_called_once_with(cenario.equipe)
        cenario.db.flush.assert_awaited_once_with()
    else:
        assert cenario.equipe.model_dump() == antes
        cenario.db.add.assert_not_called()
        cenario.db.flush.assert_not_awaited()
    if esperado == SituacaoEquipe.HOMOLOGADA and esperado != situacao:
        cenario.avisar_equipe_homologada.assert_awaited_once_with(cenario.db, cenario.equipe)
        cenario.notificar_equipe_homologada.assert_awaited_once_with(cenario.db, cenario.equipe)
    else:
        cenario.avisar_equipe_homologada.assert_not_awaited()
        cenario.notificar_equipe_homologada.assert_not_awaited()
    cenario.db.commit.assert_not_awaited()
