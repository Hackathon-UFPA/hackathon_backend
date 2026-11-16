from app.const.enums import PapelUsuario

# Hierarquia de cadastro (RF06, RF07, RF08): quem pode criar usuários de cada perfil.
# Não é herança de permissões: um perfil só faz o que está descrito aqui e nas rotas que o exigem.
# O Organizador pode cadastrar qualquer perfil de negócio; DEV é uma exceção interna do time de
# desenvolvimento e só é criado por outro DEV (ou pelo script de apoio).
PERFIS_QUE_CADASTRAM: dict[PapelUsuario, frozenset[PapelUsuario]] = {
    PapelUsuario.ORGANIZADOR: frozenset(PapelUsuario) - {PapelUsuario.DEV},
    PapelUsuario.COMITE_CIENTIFICO: frozenset({PapelUsuario.COMITE_TECNICO, PapelUsuario.MENTOR}),
}


def perfis_cadastraveis(quem_cadastra: PapelUsuario) -> list[PapelUsuario]:
    """Perfis que `quem_cadastra` pode criar, na ordem do enum."""
    if quem_cadastra == PapelUsuario.DEV:
        return list(PapelUsuario)
    permitidos = PERFIS_QUE_CADASTRAM.get(quem_cadastra, frozenset())
    return [papel for papel in PapelUsuario if papel in permitidos]


def pode_cadastrar(quem_cadastra: PapelUsuario, perfil: PapelUsuario) -> bool:
    return perfil in perfis_cadastraveis(quem_cadastra)


# Gestão de contas (RN24, BE-S5-07): quem pode cadastrar um perfil também pode editá-lo,
# desativá-lo e reativá-lo. O Comitê Científico gerencia Comitê Técnico e Mentor; o Organizador,
# todos menos DEV.
def pode_gerenciar(quem_gerencia: PapelUsuario, perfil: PapelUsuario) -> bool:
    return pode_cadastrar(quem_gerencia, perfil)


# Perfis entre os quais um gestor pode mover uma conta. Participante fica de fora porque tem
# equipe, inscrição e comprovante; Mentor, porque segue o fluxo próprio de ativação (RN33); DEV,
# por ser exceção interna. Quem recebe o novo perfil também precisa estar no alcance do gestor.
PAPEIS_TROCAVEIS = frozenset(
    {PapelUsuario.COMITE_TECNICO, PapelUsuario.COMITE_CIENTIFICO, PapelUsuario.ORGANIZADOR}
)


def pode_trocar_papel(quem_gerencia: PapelUsuario, de: PapelUsuario, para: PapelUsuario) -> bool:
    return (
        de in PAPEIS_TROCAVEIS
        and para in PAPEIS_TROCAVEIS
        and pode_gerenciar(quem_gerencia, de)
        and pode_gerenciar(quem_gerencia, para)
    )


# Quem confere o comprovante de vínculo (RF21). A Q25 ainda não decidiu se é só o Organizador ou
# também o Comitê Científico; enquanto isso os dois podem. Ajustar aqui muda todas as rotas.
PERFIS_QUE_VALIDAM_COMPROVANTE = (PapelUsuario.ORGANIZADOR, PapelUsuario.COMITE_CIENTIFICO)

# Quem cadastra e configura as edições do hackathon (datas, limites). DEV passa sempre.
PERFIS_QUE_GERENCIAM_EDITAL = (PapelUsuario.ORGANIZADOR,)

# Quem gerencia temas/desafios e monta/publica as rubricas (RF15, RF16, RF17, BE-S5-08).
# O Comitê Científico é o responsável; o Organizador entra como exceção administrativa.
# DEV passa sempre.
PERFIS_QUE_GERENCIAM_TEMAS_E_RUBRICAS = (PapelUsuario.COMITE_CIENTIFICO, PapelUsuario.ORGANIZADOR)

# Quem vê todas as sessões e materiais do treinamento, além das equipes aprovadas (RF35). DEV passa
# sempre.
PERFIS_QUE_ACOMPANHAM_TREINAMENTO = (PapelUsuario.ORGANIZADOR, PapelUsuario.COMITE_CIENTIFICO)

# Quem acompanha a fila de e-mails e pede o reenvio dos que falharam (RNF28). DEV passa sempre.
PERFIS_QUE_ACOMPANHAM_EMAILS = (PapelUsuario.ORGANIZADOR,)
