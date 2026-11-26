[← Voltar ao README](../README.md)

# Designação dos projetos finais ao Comitê Técnico — BE-S6-09

RF47, RF48, RN11, RN13 e Q07 (2 a 3 avaliadores por projeto). Todas as rotas exigem token e conta ativa. Segue o padrão da distribuição das propostas ([avaliacao.md](avaliacao.md)), mas em tabelas próprias: **não se mistura com a avaliação científica**.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `PATCH /admin/hackathons/{id}/avaliacao-tecnica/configuracao` | Organizador (e DEV) | Define `avaliadores_por_projeto_final` (2 ou 3) |
| `POST /admin/hackathons/{id}/avaliacao-tecnica/distribuir` | Organizador (e DEV) | Distribui os projetos finais entre o Comitê Técnico |
| `PUT /admin/projetos-finais/{submissao_id}/avaliadores` | Organizador (e DEV) | Redistribui um projeto: troca os avaliadores pela lista `avaliador_ids` |
| `GET /admin/hackathons/{id}/avaliacao-tecnica/designacoes` | Organizador (e DEV) | Cada projeto final com os avaliadores vigentes |
| `POST /admin/hackathons/{id}/avaliacao-tecnica/conflitos` | Organizador (e DEV) | Registra conflito de interesse avaliador × equipe (`motivo` obrigatório) |
| `GET /admin/hackathons/{id}/avaliacao-tecnica/conflitos` | Organizador (e DEV) | Conflitos declarados no hackathon |
| `GET /comite-tecnico/projetos-finais` | Comitê Técnico (e DEV) | Só os projetos designados a quem está logado (sem a equipe) |
| `GET /comite-tecnico/projetos-finais/{submissao_id}` | Comitê Técnico (e DEV) | Um projeto designado; qualquer outro responde 404 |

**O que é projeto final.** Cada proposta **aprovada** na homologação do resultado científico (`resultados_proposta.aprovada = true`, RF31). Antes da homologação, distribuir e listar respondem 409. O identificador do projeto é o `submissao_id` da proposta aprovada; a submissão final (BE-S6-07) poderá ser ligada ao mesmo projeto depois.

**Quantidade.** `hackathon.avaliadores_por_projeto_final` tem `CHECK` entre 2 e 3 e não tem valor padrão (409 enquanto `NULL`). Alterar vale só para as próximas distribuições.

**Quem é elegível.** `papel = COMITE_TECNICO`, `ativo = true`, `situacao_conta = ATIVA` e mesma organização do hackathon. Comitê Científico não entra.

**Conflito de interesse (RN13).** Não pode ser designado ao projeto de uma equipe:
- quem é integrante dela (`membros_equipe`);
- quem é ou foi mentor dela (`atribuicoes_mentor`, inclusive atribuições encerradas);
- quem tem conflito declarado pelo Organizador (`conflitos_projeto_final`).

Registrar um conflito para quem já está designado ao projeto responde 409: redistribua antes. Conflito repetido também responde 409. Conflitos não são apagados.

**Distribuição.** Completa cada projeto até N avaliadores, sempre com quem tem menos projetos no hackathon (desempate pelo id). Rodar de novo só completa o que falta. Se faltar avaliador sem conflito para qualquer projeto, responde 409 e **nada é gravado**. A linha do hackathon fica travada (`SELECT ... FOR UPDATE`) durante a operação, então distribuições simultâneas não duplicam designações.

**Redistribuição e auditoria.** O `PUT` recebe exatamente N ids distintos (422 caso contrário), todos elegíveis (409) e sem conflito com a equipe (409, com os ids no `detail`). Quem continua mantém a designação original. **Nada é apagado:** quem sai fica em `designacoes_projeto_final` com `removida_em` e `removida_por`. O índice parcial `uq_designacoes_projeto_final_vigente` impede duas designações vigentes iguais.

**Bloqueios.** Hackathon `FINALIZADO` ou `CANCELADO` bloqueia configurar, distribuir, redistribuir e registrar conflito (409).

**Pendente para a BE-S6-10.** Quando existir a avaliação técnica, distribuir deve pular projetos com avaliação iniciada e redistribuir deve recusá-los (como a avaliação científica faz), e a avaliação deve exigir designação vigente.
