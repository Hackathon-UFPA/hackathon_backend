from enum import Enum, StrEnum

from sqlalchemy import Enum as SAEnum


class PapelUsuario(StrEnum):
    PARTICIPANTE = "PARTICIPANTE"
    PROFESSOR = "PROFESSOR"
    COORDENADOR = "COORDENADOR"
    AVALIADOR = "AVALIADOR"
    MENTOR = "MENTOR"
    DEV = "DEV"


class StatusHackathon(StrEnum):
    RASCUNHO = "RASCUNHO"
    INSCRICOES = "INSCRICOES"
    INSCRICOES_ENCERRADAS = "INSCRICOES_ENCERRADAS"
    ATIVO = "ATIVO"
    EM_AVALIACAO = "EM_AVALIACAO"
    FINALIZADO = "FINALIZADO"
    CANCELADO = "CANCELADO"


class FuncaoMembro(StrEnum):
    LIDER = "LIDER"
    DESENVOLVEDOR = "DESENVOLVEDOR"
    DESIGNER = "DESIGNER"
    NEGOCIOS = "NEGOCIOS"
    OUTRO = "OUTRO"


class CategoriaArtefato(StrEnum):
    REPOSITORIO_CODIGO = "REPOSITORIO_CODIGO"
    DIAGRAMA = "DIAGRAMA"
    VIDEO = "VIDEO"
    APRESENTACAO = "APRESENTACAO"
    DOCUMENTACAO = "DOCUMENTACAO"
    PROTOTIPO = "PROTOTIPO"
    OUTRO = "OUTRO"


def pg_enum(enum_cls: type[Enum], nome: str):
    """Mapeia um Enum Python para o tipo ENUM nativo do Postgres (criado pelo Flyway)."""
    return SAEnum(
        enum_cls,
        name=nome,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )
