from enum import Enum, StrEnum

from sqlalchemy import Enum as SAEnum


# Perfis do RF06. Líder técnico não é papel: é membros_equipe.funcao = LIDER
class PapelUsuario(StrEnum):
    PARTICIPANTE = "PARTICIPANTE"
    MENTOR = "MENTOR"
    COMITE_TECNICO = "COMITE_TECNICO"
    COMITE_CIENTIFICO = "COMITE_CIENTIFICO"
    ORGANIZADOR = "ORGANIZADOR"
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


class SituacaoEquipe(StrEnum):
    EM_FORMACAO = "EM_FORMACAO"
    AGUARDANDO_HOMOLOGACAO = "AGUARDANDO_HOMOLOGACAO"
    HOMOLOGADA = "HOMOLOGADA"
    NAO_HOMOLOGADA = "NAO_HOMOLOGADA"


class StatusConvite(StrEnum):
    PENDENTE = "PENDENTE"
    ACEITO = "ACEITO"
    RECUSADO = "RECUSADO"
    CANCELADO = "CANCELADO"


class TipoTermo(StrEnum):
    REGULAMENTO = "REGULAMENTO"
    TERMO_CONSENTIMENTO = "TERMO_CONSENTIMENTO"


class StatusComprovante(StrEnum):
    PENDENTE = "PENDENTE"
    APROVADO = "APROVADO"
    RECUSADO = "RECUSADO"


class StatusProposta(StrEnum):
    RASCUNHO = "RASCUNHO"
    ENVIADA = "ENVIADA"


class TipoProtocolo(StrEnum):
    INSCRICAO_EQUIPE = "INSCRICAO_EQUIPE"
    PROPOSTA = "PROPOSTA"


def pg_enum(enum_cls: type[Enum], nome: str):
    """Mapeia um Enum Python para o tipo ENUM nativo do Postgres (criado pelo Flyway)."""
    return SAEnum(
        enum_cls,
        name=nome,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )
