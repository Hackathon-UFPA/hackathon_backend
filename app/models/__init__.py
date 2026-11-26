"""
Models: tabelas do banco com SQLModel (`table=True`). Um arquivo por tabela.

A estrutura da tabela no banco é criada pelas migrations do Flyway (pasta `migrations/`);
o model precisa refletir exatamente essa estrutura.

Exemplo (models/produto.py):

    from uuid import UUID, uuid4
    from sqlmodel import Field, SQLModel

    class Produto(SQLModel, table=True):
        __tablename__ = "produto"

        id: UUID = Field(default_factory=uuid4, primary_key=True)
        nome: str = Field(max_length=255, nullable=False)
"""

from .aceite_termo import AceiteTermo
from .apoiador import Apoiador
from .artefato import Artefato
from .atribuicao_mentor import AtribuicaoMentor
from .autodeclaracao_vinculo import AutodeclaracaoVinculo
from .avaliacao import Avaliacao
from .comprovante_vinculo import ComprovanteVinculo
from .convite import Convite
from .convite_mentor import ConviteMentor
from .criterio_rubrica import CriterioRubrica
from .designacao_avaliacao import DesignacaoAvaliacao
from .designacao_projeto_final import ConflitoProjetoFinal, DesignacaoProjetoFinal
from .email_outbox import EmailOutbox
from .entrega_mentoria import EntregaMentoria
from .equipe import Equipe
from .evento_mentoria import EventoNotificacaoMentoria
from .faq_item import FaqItem
from .fase_cronograma import FaseCronograma
from .feedback_mentoria import FeedbackMentoria
from .hackathon import Hackathon
from .marco_mentoria import MarcoMentoria
from .material_treinamento import MaterialTreinamento
from .membro_equipe import MembroEquipe
from .nota_criterio_avaliacao import NotaCriterioAvaliacao
from .notificacao import Notificacao, NotificacaoResultado
from .organizacao import Organizacao
from .protocolo import Protocolo
from .resultado import HomologacaoResultado, ResultadoProposta
from .rubrica import Rubrica
from .sessao_treinamento import SessaoTreinamento
from .submissao import Submissao
from .submissao_final import SubmissaoFinal
from .tema import Tema
from .termo import Termo
from .token_usuario import TokenUsuario
from .usuario import Usuario
from .versao_proposta import VersaoProposta

__all__ = [
    "AceiteTermo",
    "Apoiador",
    "Artefato",
    "AutodeclaracaoVinculo",
    "AtribuicaoMentor",
    "Avaliacao",
    "ComprovanteVinculo",
    "Convite",
    "ConviteMentor",
    "CriterioRubrica",
    "DesignacaoAvaliacao",
    "DesignacaoProjetoFinal",
    "ConflitoProjetoFinal",
    "EmailOutbox",
    "EntregaMentoria",
    "Equipe",
    "FaqItem",
    "FeedbackMentoria",
    "FaseCronograma",
    "EventoNotificacaoMentoria",
    "Hackathon",
    "HomologacaoResultado",
    "MarcoMentoria",
    "MaterialTreinamento",
    "MembroEquipe",
    "NotaCriterioAvaliacao",
    "Notificacao",
    "NotificacaoResultado",
    "Organizacao",
    "Protocolo",
    "ResultadoProposta",
    "Rubrica",
    "SessaoTreinamento",
    "Submissao",
    "SubmissaoFinal",
    "Tema",
    "Termo",
    "TokenUsuario",
    "Usuario",
    "VersaoProposta",
]
