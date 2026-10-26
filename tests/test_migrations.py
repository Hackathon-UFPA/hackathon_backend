"""
Testes da migration V202610261200 (fluxos de inscrição e proposta e perfis de acesso).

Cada teste roda numa transação desfeita no final, então não deixa dados no banco.
Os casos inválidos conferem o nome da constraint que barrou o dado.
"""

import asyncio
import re
from enum import StrEnum
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import app.const.enums as enums
import app.models  # noqa: F401  (registra as tabelas no SQLModel.metadata)
from app.const.config import settings
from app.const.enums import PapelUsuario, TipoProtocolo, TipoTermo
from app.models import AceiteTermo, Equipe, Hackathon, Protocolo, Termo, Usuario


def rodar(fn):
    """Executa `fn(conn)` numa transação que é desfeita no final."""

    async def main():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                trans = await conn.begin()
                try:
                    return await fn(conn)
                finally:
                    await trans.rollback()
        finally:
            await engine.dispose()

    return asyncio.run(main())


async def sql(conn, comando, **params):
    resultado = await conn.execute(text(comando), params)
    return resultado.scalar_one_or_none() if resultado.returns_rows else None


async def novo_hackathon(conn):
    return await sql(conn, "INSERT INTO hackathon (nome) VALUES ('Teste') RETURNING id")


async def novo_usuario(conn):
    return await sql(
        conn,
        "INSERT INTO usuarios (email, papel) VALUES (:email, 'PARTICIPANTE') RETURNING id",
        email=f"{uuid4()}@teste.com",
    )


async def nova_equipe(conn, hackathon_id):
    return await sql(
        conn, "INSERT INTO equipes (hackathon_id) VALUES (:h) RETURNING id", h=hackathon_id
    )


async def novo_membro(conn, equipe_id, hackathon_id, usuario_id, funcao=None):
    await sql(
        conn,
        "INSERT INTO membros_equipe (equipe_id, hackathon_id, usuario_id, funcao)"
        " VALUES (:e, :h, :u, CAST(:f AS funcao_membro))",
        e=equipe_id,
        h=hackathon_id,
        u=usuario_id,
        f=funcao,
    )


async def novo_tema(conn, hackathon_id):
    return await sql(
        conn,
        "INSERT INTO temas (hackathon_id, titulo, ods) VALUES (:h, :t, '{13}') RETURNING id",
        h=hackathon_id,
        t=f"Tema {uuid4()}",
    )


async def novo_termo(conn, hackathon_id, versao="1.0", vigente=False):
    return await sql(
        conn,
        "INSERT INTO termos (hackathon_id, tipo, versao, titulo, url, vigente)"
        " VALUES (:h, 'REGULAMENTO', :v, 'Regulamento', 'https://x', :vig) RETURNING id",
        h=hackathon_id,
        v=versao,
        vig=vigente,
    )


async def novo_comprovante(conn, usuario_id, hackathon_id, status="PENDENTE", motivo=None):
    validado = "NULL" if status == "PENDENTE" else "now()"
    return await sql(
        conn,
        "INSERT INTO comprovantes_vinculo"
        " (usuario_id, hackathon_id, arquivo_url, status, motivo_recusa, validado_em)"
        f" VALUES (:u, :h, 'https://x.pdf', CAST(:s AS status_comprovante), :m, {validado})"
        " RETURNING id",
        u=usuario_id,
        h=hackathon_id,
        s=status,
        m=motivo,
    )


def test_migration_aplicada():
    async def fn(conn):
        return await sql(
            conn, "SELECT success FROM flyway_schema_history WHERE version = '202610261200'"
        )

    assert rodar(fn) is True


def test_enums_batem_com_banco():
    """Cada StrEnum de app/const/enums.py tem os valores (e a ordem) do tipo no banco."""

    async def fn(conn):
        linhas = await conn.execute(
            text(
                "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)"
                " FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid GROUP BY t.typname"
            )
        )
        return dict(linhas.all())

    banco = rodar(fn)
    python = {
        nome: [m.value for m in cls]
        for nome, cls in vars(enums).items()
        if isinstance(cls, type) and issubclass(cls, StrEnum) and cls is not StrEnum
    }
    assert len(python) == len(banco)
    for cls in python:
        tipo = re.sub(r"(?<!^)(?=[A-Z])", "_", cls).lower()
        assert python[cls] == banco[tipo], f"{cls} diverge do tipo {tipo} no banco"


def test_models_batem_com_banco():
    """Cada model tem exatamente as colunas da tabela, com o mesmo nullable."""

    async def fn(conn):
        def colunas(sync_conn):
            insp = inspect(sync_conn)
            return {
                tabela.name: {c["name"]: c["nullable"] for c in insp.get_columns(tabela.name)}
                for tabela in SQLModel.metadata.sorted_tables
            }

        return await conn.run_sync(colunas)

    banco = rodar(fn)
    for tabela in SQLModel.metadata.sorted_tables:
        model = {c.name: c.nullable for c in tabela.columns}
        assert model == banco[tabela.name], f"model e banco divergem em {tabela.name}"


def test_orm_usa_padroes_do_banco():
    """Data do aceite e número do protocolo vêm do banco quando o model não envia valor."""

    async def fn(conn):
        session = AsyncSession(bind=conn)
        hackathon = Hackathon(nome="Teste")
        usuario = Usuario(email=f"{uuid4()}@teste.com", papel=PapelUsuario.PARTICIPANTE)
        session.add_all([hackathon, usuario])
        await session.flush()
        equipe = Equipe(hackathon_id=hackathon.id)
        termo = Termo(
            hackathon_id=hackathon.id, tipo=TipoTermo.REGULAMENTO, versao="1", titulo="R", url="x"
        )
        session.add_all([equipe, termo])
        await session.flush()
        aceite = AceiteTermo(termo_id=termo.id, usuario_id=usuario.id)
        protocolo = Protocolo(tipo=TipoProtocolo.INSCRICAO_EQUIPE, equipe_id=equipe.id)
        session.add_all([aceite, protocolo])
        await session.flush()
        await session.refresh(aceite)
        await session.refresh(protocolo)
        await session.refresh(equipe)
        return aceite.aceito_em, protocolo.numero, protocolo.emitido_em, equipe.situacao

    aceito_em, numero, emitido_em, situacao = rodar(fn)
    assert aceito_em is not None
    assert emitido_em is not None
    assert re.fullmatch(r"HK\d{4}-\d{6}", numero)
    assert situacao == "EM_FORMACAO"


# --- Equipe e membros (RN01, RN02) ---


def test_pessoa_em_duas_equipes_do_mesmo_hackathon():
    async def fn(conn):
        h = await novo_hackathon(conn)
        u = await novo_usuario(conn)
        await novo_membro(conn, await nova_equipe(conn, h), h, u)
        await novo_membro(conn, await nova_equipe(conn, h), h, u)

    with pytest.raises(IntegrityError, match="uq_membros_equipe_hackathon_usuario"):
        rodar(fn)


def test_pessoa_em_equipes_de_hackathons_diferentes():
    async def fn(conn):
        u = await novo_usuario(conn)
        for _ in range(2):
            h = await novo_hackathon(conn)
            await novo_membro(conn, await nova_equipe(conn, h), h, u)

    rodar(fn)


def test_membro_com_hackathon_diferente_do_da_equipe():
    async def fn(conn):
        equipe = await nova_equipe(conn, await novo_hackathon(conn))
        await novo_membro(conn, equipe, await novo_hackathon(conn), await novo_usuario(conn))

    with pytest.raises(IntegrityError, match="fk_membros_equipe_equipe_hackathon"):
        rodar(fn)


def test_um_lider_por_equipe():
    async def fn(conn):
        h = await novo_hackathon(conn)
        e = await nova_equipe(conn, h)
        await novo_membro(conn, e, h, await novo_usuario(conn), "LIDER")
        await novo_membro(conn, e, h, await novo_usuario(conn), "LIDER")

    with pytest.raises(IntegrityError, match="uq_membros_equipe_lider"):
        rodar(fn)


def test_min_integrantes_maior_que_max():
    async def fn(conn):
        await sql(conn, "INSERT INTO hackathon (min_integrantes, max_integrantes) VALUES (6, 5)")

    with pytest.raises(IntegrityError, match="ck_hackathon_integrantes"):
        rodar(fn)


# --- Convites (RF18, RF19) ---


async def novo_convite(conn, equipe_id, convidado_por, email, status="PENDENTE"):
    respondido = "now()" if status in ("ACEITO", "RECUSADO") else "NULL"
    await sql(
        conn,
        "INSERT INTO convites (equipe_id, nome, email, convidado_por, status, respondido_em)"
        f" VALUES (:e, 'Fulano', :email, :c, CAST(:s AS status_convite), {respondido})",
        e=equipe_id,
        email=email,
        c=convidado_por,
        s=status,
    )


def test_convite_pendente_repetido():
    async def fn(conn):
        e = await nova_equipe(conn, await novo_hackathon(conn))
        lider = await novo_usuario(conn)
        await novo_convite(conn, e, lider, "maria@teste.com")
        await novo_convite(conn, e, lider, "MARIA@teste.com")

    with pytest.raises(IntegrityError, match="uq_convites_equipe_email_ativo"):
        rodar(fn)


def test_novo_convite_depois_de_recusa():
    async def fn(conn):
        e = await nova_equipe(conn, await novo_hackathon(conn))
        lider = await novo_usuario(conn)
        await novo_convite(conn, e, lider, "maria@teste.com", "RECUSADO")
        await novo_convite(conn, e, lider, "maria@teste.com")

    rodar(fn)


def test_convite_aceito_sem_data_de_resposta():
    async def fn(conn):
        e = await nova_equipe(conn, await novo_hackathon(conn))
        await sql(
            conn,
            "INSERT INTO convites (equipe_id, nome, email, convidado_por, status)"
            " VALUES (:e, 'Fulano', 'f@teste.com', :c, 'ACEITO')",
            e=e,
            c=await novo_usuario(conn),
        )

    with pytest.raises(IntegrityError, match="ck_convites_resposta"):
        rodar(fn)


# --- Termos e aceites (RF20, RN05) ---


def test_aceite_duplicado():
    async def fn(conn):
        termo = await novo_termo(conn, await novo_hackathon(conn))
        u = await novo_usuario(conn)
        for _ in range(2):
            await sql(
                conn,
                "INSERT INTO aceites_termos (termo_id, usuario_id) VALUES (:t, :u)",
                t=termo,
                u=u,
            )

    with pytest.raises(IntegrityError, match="uq_aceites_termos_termo_usuario"):
        rodar(fn)


def test_duas_versoes_vigentes_do_mesmo_termo():
    async def fn(conn):
        h = await novo_hackathon(conn)
        await novo_termo(conn, h, "1.0", vigente=True)
        await novo_termo(conn, h, "2.0", vigente=True)

    with pytest.raises(IntegrityError, match="uq_termos_vigente"):
        rodar(fn)


def test_termo_sem_conteudo_nem_url():
    async def fn(conn):
        await sql(
            conn,
            "INSERT INTO termos (hackathon_id, tipo, versao, titulo)"
            " VALUES (:h, 'REGULAMENTO', '1.0', 'Regulamento')",
            h=await novo_hackathon(conn),
        )

    with pytest.raises(IntegrityError, match="ck_termos_conteudo"):
        rodar(fn)


# --- Comprovante de vínculo (RF21, RN25) ---


def test_comprovante_recusado_sem_motivo():
    async def fn(conn):
        await novo_comprovante(
            conn, await novo_usuario(conn), await novo_hackathon(conn), "RECUSADO"
        )

    with pytest.raises(IntegrityError, match="ck_comprovantes_motivo"):
        rodar(fn)


def test_reenvio_de_comprovante_depois_de_recusa():
    async def fn(conn):
        u, h = await novo_usuario(conn), await novo_hackathon(conn)
        await novo_comprovante(conn, u, h, "RECUSADO", "Documento ilegível")
        await novo_comprovante(conn, u, h)

    rodar(fn)


def test_dois_comprovantes_pendentes():
    async def fn(conn):
        u, h = await novo_usuario(conn), await novo_hackathon(conn)
        await novo_comprovante(conn, u, h)
        await novo_comprovante(conn, u, h)

    with pytest.raises(IntegrityError, match="uq_comprovantes_vinculo_ativo"):
        rodar(fn)


# --- Temas e proposta (RF15, RF26, RF27, RN04) ---


async def nova_submissao(conn, equipe_id, hackathon_id, **campos):
    colunas = ", ".join(["equipe_id", "hackathon_id", *campos])
    valores = ", ".join([":equipe_id", ":hackathon_id", *(f":{c}" for c in campos)])
    return await sql(
        conn,
        f"INSERT INTO submissoes ({colunas}) VALUES ({valores}) RETURNING id",
        equipe_id=equipe_id,
        hackathon_id=hackathon_id,
        **campos,
    )


def test_tema_com_ods_invalido():
    async def fn(conn):
        await sql(
            conn,
            "INSERT INTO temas (hackathon_id, titulo, ods) VALUES (:h, 'Tema', '{18}')",
            h=await novo_hackathon(conn),
        )

    with pytest.raises(IntegrityError, match="ck_temas_ods"):
        rodar(fn)


def test_rascunho_incompleto_e_aceito():
    async def fn(conn):
        h = await novo_hackathon(conn)
        s = await nova_submissao(conn, await nova_equipe(conn, h), h)
        return await sql(conn, "SELECT status::text FROM submissoes WHERE id = :s", s=s)

    assert rodar(fn) == "RASCUNHO"


def test_proposta_enviada_sem_tema():
    async def fn(conn):
        h = await novo_hackathon(conn)
        await sql(
            conn,
            "INSERT INTO submissoes (equipe_id, hackathon_id, status, titulo, descricao, ods,"
            " bases_dados, enviado_em)"
            " VALUES (:e, :h, 'ENVIADA', 'T', 'D', '{11}', 'IBGE', now())",
            e=await nova_equipe(conn, h),
            h=h,
        )

    with pytest.raises(IntegrityError, match="ck_submissoes_enviada"):
        rodar(fn)


def test_proposta_enviada_completa():
    async def fn(conn):
        h = await novo_hackathon(conn)
        await sql(
            conn,
            "INSERT INTO submissoes (equipe_id, hackathon_id, tema_id, status, titulo, descricao,"
            " ods, bases_dados, enviado_em)"
            " VALUES (:e, :h, :t, 'ENVIADA', 'T', 'D', '{11}', 'IBGE', now())",
            e=await nova_equipe(conn, h),
            h=h,
            t=await novo_tema(conn, h),
        )

    rodar(fn)


def test_duas_propostas_da_mesma_equipe():
    async def fn(conn):
        h = await novo_hackathon(conn)
        e = await nova_equipe(conn, h)
        await nova_submissao(conn, e, h)
        await nova_submissao(conn, e, h)

    with pytest.raises(IntegrityError, match="uq_submissoes_equipe"):
        rodar(fn)


def test_proposta_com_tema_de_outro_hackathon():
    async def fn(conn):
        h = await novo_hackathon(conn)
        tema_de_outro = await novo_tema(conn, await novo_hackathon(conn))
        await nova_submissao(conn, await nova_equipe(conn, h), h, tema_id=tema_de_outro)

    with pytest.raises(IntegrityError, match="fk_submissoes_tema_hackathon"):
        rodar(fn)


# --- Protocolos (RF22, RF28) ---


def test_protocolo_de_proposta_sem_submissao():
    async def fn(conn):
        e = await nova_equipe(conn, await novo_hackathon(conn))
        await sql(conn, "INSERT INTO protocolos (tipo, equipe_id) VALUES ('PROPOSTA', :e)", e=e)

    with pytest.raises(IntegrityError, match="ck_protocolos_proposta"):
        rodar(fn)


# --- Perfis de acesso (RF06, RF07, RF37) ---


def test_usuario_novo_fica_ativo():
    async def fn(conn):
        return await sql(
            conn, "SELECT ativo FROM usuarios WHERE id = :u", u=await novo_usuario(conn)
        )

    assert rodar(fn) is True


def test_papel_antigo_nao_existe_mais():
    async def fn(conn):
        await sql(conn, "INSERT INTO usuarios (email, papel) VALUES ('p@teste.com', 'PROFESSOR')")

    with pytest.raises(DBAPIError, match="papel_usuario"):
        rodar(fn)


def test_mentor_com_max_equipes_zero():
    async def fn(conn):
        await sql(
            conn,
            "INSERT INTO usuarios (email, papel, max_equipes) VALUES ('m@teste.com', 'MENTOR', 0)",
        )

    with pytest.raises(IntegrityError, match="ck_usuarios_max_equipes"):
        rodar(fn)
