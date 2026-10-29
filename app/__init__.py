# Tags de agrupamento do swagger. Adicione uma entrada para cada router novo.
tags = [
    {"name": "Health", "description": "Verificação de saúde da API e do banco de dados"},
    {"name": "Autenticação", "description": "Cadastro de participante e login (RF01, RF02)"},
    {"name": "Usuários", "description": "Cadastro de usuários de outros perfis (RF07, RF08)"},
    {
        "name": "Equipes",
        "description": "Criação, consulta e edição de equipes e membros (RF18, RF24)",
    },
    {
        "name": "Convites",
        "description": "Convidar integrantes, aceitar ou recusar convites (RF18, RF19)",
    },
    {
        "name": "Termos",
        "description": "Regulamento e termo de consentimento vigentes e seus aceites (RF20)",
    },
    {
        "name": "Comprovantes",
        "description": "Conferência e reenvio do comprovante de vínculo (RF21, RN25)",
    },
    {
        "name": "Inscrição",
        "description": "Painel da equipe, conclusão da inscrição e homologação (RF22, RF23, RF25)",
    },
    {"name": "Propostas", "description": "Criação, consulta e edição de rascunhos (RF27)"},
]
