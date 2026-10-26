from app.const.enums import PapelUsuario

# Hierarquia de cadastro (RF06, RF07, RF08): quem pode criar usuários de cada perfil.
# Não é herança de permissões: um perfil só faz o que está descrito aqui e nas rotas que o exigem.
# O Organizador pode cadastrar qualquer perfil de negócio; DEV é uma exceção interna do time de
# desenvolvimento e só é criado por outro DEV (ou pelo script de apoio).
PERFIS_QUE_CADASTRAM: dict[PapelUsuario, frozenset[PapelUsuario]] = {
    PapelUsuario.ORGANIZADOR: frozenset(PapelUsuario) - {PapelUsuario.DEV},
    PapelUsuario.COMITE_CIENTIFICO: frozenset({PapelUsuario.COMITE_TECNICO, PapelUsuario.MENTOR}),
}


def pode_cadastrar(quem_cadastra: PapelUsuario, perfil: PapelUsuario) -> bool:
    if quem_cadastra == PapelUsuario.DEV:
        return True
    return perfil in PERFIS_QUE_CADASTRAM.get(quem_cadastra, frozenset())
