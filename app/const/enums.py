from enum import Enum, StrEnum

from sqlalchemy import Enum as SAEnum


# Perfis do RF06. Líder técnico não é papel: é membros_equipe.funcao = LIDER
class PapelUsuario(StrEnum):
    PARTICIPANTE = "PARTICIPANTE"
    MENTOR = "MENTOR"
    COMITE_TECNICO = "COMITE_TECNICO"
    COMITE_CIENTIFICO = "COMITE_CIENTIFICO"
    ORGANIZADOR = "ORGANIZADOR"
    # Time de desenvolvimento: acesso a todas as rotas para testes (exceção à RN24)
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


class StatusAvaliacao(StrEnum):
    RASCUNHO = "RASCUNHO"
    ENVIADA = "ENVIADA"


class RecomendacaoAvaliacao(StrEnum):
    APROVACAO = "APROVACAO"
    REPROVACAO = "REPROVACAO"


class CanalNotificacao(StrEnum):
    PLATAFORMA = "PLATAFORMA"
    EMAIL = "EMAIL"  # reservado: depende da decisão Q16 e da infraestrutura de e-mail


class StatusEnvioNotificacao(StrEnum):
    PENDENTE = "PENDENTE"
    ENVIADO = "ENVIADO"
    FALHA = "FALHA"


class SituacaoConta(StrEnum):
    PENDENTE = "PENDENTE"
    ATIVA = "ATIVA"


class TipoEmail(StrEnum):
    """Cada tipo tem um template em `app/templates/emails/` (RNF28, RF60)."""

    CONFIRMACAO_EMAIL = "CONFIRMACAO_EMAIL"
    RECUPERACAO_SENHA = "RECUPERACAO_SENHA"
    DEFINICAO_SENHA = "DEFINICAO_SENHA"
    CONVITE_EQUIPE = "CONVITE_EQUIPE"
    INSCRICAO_CONCLUIDA = "INSCRICAO_CONCLUIDA"
    EQUIPE_HOMOLOGADA = "EQUIPE_HOMOLOGADA"
    PROTOCOLO_PROPOSTA = "PROTOCOLO_PROPOSTA"
    RESULTADO_PROPOSTA = "RESULTADO_PROPOSTA"
    ATRIBUICAO_MENTOR = "ATRIBUICAO_MENTOR"


class StatusEmail(StrEnum):
    PENDENTE = "PENDENTE"  # na fila: ainda não tentou, ou aguardando a próxima tentativa
    ENVIANDO = "ENVIANDO"  # reservado por um worker
    ENVIADO = "ENVIADO"  # o provedor aceitou a mensagem
    FALHA = "FALHA"  # erro permanente ou tentativas esgotadas; só sai daqui com reenvio manual


def pg_enum(enum_cls: type[Enum], nome: str):
    """Mapeia um Enum Python para o tipo ENUM nativo do Postgres (criado pelo Flyway)."""
    return SAEnum(
        enum_cls,
        name=nome,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )
