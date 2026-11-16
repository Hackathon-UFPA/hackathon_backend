"""Política de categoria da equipe e coerência dos tipos de integrante (BE-S5-01).

Decisão de 05/11: o líder informa a categoria (ESTUDANTES, PROFISSIONAIS ou MISTA) e o tipo de
cada pessoa. A regra antiga da Sprint 2 (só graduandos com vínculo acadêmico) não vale para todos:
o vínculo exigido depende do tipo indicado, e quais categorias a edição aceita é configuração do
hackathon (`aceita_equipe_*`), provisória até o Squad 1 validar.
"""

from collections.abc import Iterable

from app.const.enums import CategoriaEquipe, TipoIntegrante
from app.exceptions.equipe import categoria_nao_permitida, composicao_invalida
from app.models import Hackathon

_CAMPO_DA_CATEGORIA = {
    CategoriaEquipe.ESTUDANTES: "aceita_equipe_estudantes",
    CategoriaEquipe.PROFISSIONAIS: "aceita_equipe_profissionais",
    CategoriaEquipe.MISTA: "aceita_equipe_mista",
}

_TIPO_UNICO_DA_CATEGORIA = {
    CategoriaEquipe.ESTUDANTES: TipoIntegrante.ESTUDANTE,
    CategoriaEquipe.PROFISSIONAIS: TipoIntegrante.PROFISSIONAL,
}


def categorias_permitidas(hackathon: Hackathon) -> list[CategoriaEquipe]:
    return [c for c in CategoriaEquipe if getattr(hackathon, _CAMPO_DA_CATEGORIA[c])]


def categoria_permitida(hackathon: Hackathon, categoria: CategoriaEquipe) -> bool:
    return bool(getattr(hackathon, _CAMPO_DA_CATEGORIA[categoria]))


def exigir_categoria_permitida(hackathon: Hackathon, categoria: CategoriaEquipe) -> None:
    if not categoria_permitida(hackathon, categoria):
        categoria_nao_permitida([c.value for c in categorias_permitidas(hackathon)])


def tipo_padrao(categoria: CategoriaEquipe) -> TipoIntegrante | None:
    """Tipo implícito da categoria. Na MISTA não há padrão: o líder precisa indicar."""
    return _TIPO_UNICO_DA_CATEGORIA.get(categoria)


def tipo_compativel(categoria: CategoriaEquipe, tipo: TipoIntegrante) -> bool:
    """Um tipo isolado cabe na categoria? (ESTUDANTES só aceita ESTUDANTE, e assim por diante)."""
    padrao = tipo_padrao(categoria)
    return padrao is None or padrao == tipo


def incoerencia_da_composicao(
    categoria: CategoriaEquipe, tipos: Iterable[TipoIntegrante]
) -> str | None:
    """Mensagem de erro se os tipos de todos os integrantes (líder incluído) não formam a
    categoria, ou None se estão coerentes. ESTUDANTES: todos estudantes. PROFISSIONAIS: todos
    profissionais. MISTA: ao menos um de cada."""
    tipos = list(tipos)
    estudantes = tipos.count(TipoIntegrante.ESTUDANTE)
    profissionais = tipos.count(TipoIntegrante.PROFISSIONAL)
    if categoria == CategoriaEquipe.ESTUDANTES and profissionais:
        return "Equipe ESTUDANTES só pode ter integrantes do tipo ESTUDANTE."
    if categoria == CategoriaEquipe.PROFISSIONAIS and estudantes:
        return "Equipe PROFISSIONAIS só pode ter integrantes do tipo PROFISSIONAL."
    if categoria == CategoriaEquipe.MISTA and not (estudantes and profissionais):
        return "Equipe MISTA precisa de ao menos um ESTUDANTE e um PROFISSIONAL."
    return None


def resolver_tipo(
    categoria: CategoriaEquipe, informado: TipoIntegrante | None, quem: str
) -> TipoIntegrante:
    """Tipo final de uma pessoa: o informado pelo líder, ou o da categoria quando ela só admite
    um. Na MISTA o tipo é obrigatório. Um tipo que a categoria não admite dá 422."""
    tipo = informado or tipo_padrao(categoria)
    if tipo is None:
        composicao_invalida(
            f"Informe o tipo (ESTUDANTE ou PROFISSIONAL) de {quem}: "
            "em equipe MISTA ele é obrigatório."
        )
    if not tipo_compativel(categoria, tipo):
        composicao_invalida(f"{quem}: o tipo {tipo} não cabe em equipe {categoria}.")
    return tipo
