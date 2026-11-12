"""Templates dos e-mails transacionais, em português (RNF07, RNF28).

Cada `TipoEmail` tem um par de arquivos em `app/templates/emails/` (`<tipo>.txt` e
`<tipo>.html`). Os e-mails trazem só um aviso e o link para a plataforma: nada de parecer, nota,
senha ou documento (RNF16, RNF17). O HTML escapa os valores recebidos automaticamente.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.const.enums import TipoEmail

DIRETORIO_TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "emails"

# Horário único de referência exibido ao usuário (RNF13): Brasília, UTC-3
BRASILIA = timezone(timedelta(hours=-3))

ASSUNTOS: dict[TipoEmail, str] = {
    TipoEmail.CONFIRMACAO_EMAIL: "Confirme o seu e-mail no Hackathon UFPA",
    TipoEmail.RECUPERACAO_SENHA: "Redefinição de senha no Hackathon UFPA",
    TipoEmail.DEFINICAO_SENHA: "Seu acesso ao Hackathon UFPA",
    TipoEmail.CONVITE_EQUIPE: "Convite para participar de uma equipe no Hackathon UFPA",
    TipoEmail.INSCRICAO_CONCLUIDA: "Inscrição concluída: protocolo {{ protocolo_numero }}",
    TipoEmail.EQUIPE_HOMOLOGADA: "Sua equipe foi homologada no Hackathon UFPA",
    TipoEmail.PROTOCOLO_PROPOSTA: "Proposta enviada: protocolo {{ protocolo_numero }}",
    TipoEmail.RESULTADO_PROPOSTA: "Resultado da sua proposta no Hackathon UFPA",
}

# Valores que cada template usa. Faltar um é erro de quem chama, nunca um e-mail pela metade.
# `link` pode ser None, e o e-mail sai sem o botão.
CONTEXTO_OBRIGATORIO: dict[TipoEmail, frozenset[str]] = {
    TipoEmail.CONFIRMACAO_EMAIL: frozenset({"nome", "link"}),
    TipoEmail.RECUPERACAO_SENHA: frozenset({"nome", "link", "validade_minutos"}),
    TipoEmail.DEFINICAO_SENHA: frozenset({"nome", "perfil", "link"}),
    TipoEmail.CONVITE_EQUIPE: frozenset({"nome", "equipe_nome", "lider_nome", "link"}),
    TipoEmail.INSCRICAO_CONCLUIDA: frozenset({"nome", "equipe_nome", "protocolo_numero", "link"}),
    TipoEmail.EQUIPE_HOMOLOGADA: frozenset({"nome", "equipe_nome", "link"}),
    TipoEmail.PROTOCOLO_PROPOSTA: frozenset(
        {"nome", "equipe_nome", "protocolo_numero", "enviado_em", "link"}
    ),
    TipoEmail.RESULTADO_PROPOSTA: frozenset({"nome", "equipe_nome", "aprovada", "link"}),
}


def data_hora_brasilia(momento: datetime) -> str:
    """dd/mm/aaaa às HH:MM no horário de Brasília. Data sem fuso é tratada como UTC."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(BRASILIA).strftime("%d/%m/%Y às %H:%M")


_ambiente = Environment(
    loader=FileSystemLoader(DIRETORIO_TEMPLATES),
    autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=False),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
_ambiente.filters["data_hora_brasilia"] = data_hora_brasilia


@dataclass(frozen=True)
class EmailRenderizado:
    assunto: str
    texto: str
    html: str


def renderizar(tipo: TipoEmail, contexto: dict) -> EmailRenderizado:
    """Gera assunto, texto e HTML. Levanta ValueError se faltar algum valor do contexto."""
    faltando = CONTEXTO_OBRIGATORIO[tipo] - contexto.keys()
    if faltando:
        raise ValueError(f"Faltam valores para o e-mail {tipo.value}: {sorted(faltando)}")
    arquivo = tipo.value.lower()
    assunto = _ambiente.from_string(ASSUNTOS[tipo]).render(**contexto)
    return EmailRenderizado(
        # Uma linha só: quebra no assunto é a porta de entrada de injeção de cabeçalhos
        assunto=" ".join(assunto.split()),
        texto=_ambiente.get_template(f"{arquivo}.txt").render(**contexto),
        html=_ambiente.get_template(f"{arquivo}.html").render(**contexto),
    )
