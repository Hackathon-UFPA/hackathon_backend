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
| `GET /comite-tecnico/projetos-finais` | Avaliador elegível, sem conflito e com designação vigente | Projetos designados e artefatos validados, quando disponíveis |
| `GET /comite-tecnico/projetos-finais/{submissao_id}` | Mesmas permissões da listagem | Um projeto designado, ou 404 se indisponível |
| `GET /comite-tecnico/projetos-finais/{submissao_id}/relatorio` | Mesmas permissões da listagem, com submissão final válida | PDF do relatório final como anexo |

**Designação antecipada.** Cada proposta **aprovada** na homologação do resultado científico
(`resultados_proposta.aprovada = true`, RF31) pode receber avaliadores. Antes da homologação,
distribuir e listar as designações administrativas respondem 409. A designação usa o
`submissao_id` da proposta científica e pode ser feita antes da submissão final da mentoria.
As designações já registradas continuam vinculadas ao mesmo identificador.

**Liberação para avaliação.** As respostas existentes acrescentam `pronto_para_avaliacao`.
Nas rotas do Comitê Técnico, `submissao_final` contém `repositorio` e `relatorio` quando há
uma submissão validada. Sem envio válido, `pronto_para_avaliacao` fica `false`,
`submissao_final` fica `null` e o download retorna 404. Os campos existentes, como
`documento_url` da proposta científica, mantêm seu significado. A consulta dos artefatos e
o download conferem a designação vigente, a elegibilidade atual e os impedimentos RN13.
Consulte [Submissão final](submissao-final.md).

**Quantidade.** `hackathon.avaliadores_por_projeto_final` tem `CHECK` entre 2 e 3 e não tem valor padrão (409 enquanto `NULL`). Alterar vale só para as próximas distribuições.

**Quem é elegível.** `papel = COMITE_TECNICO`, `ativo = true`, `situacao_conta = ATIVA` e mesma organização do hackathon. Comitê Científico não entra.

**Conflito de interesse (RN13).** Não pode ser designado ao projeto de uma equipe:
- quem é integrante dela (`membros_equipe`);
- quem é ou foi mentor dela (`atribuicoes_mentor`, inclusive atribuições encerradas);
- quem tem conflito declarado pelo Organizador (`conflitos_projeto_final`).

Registrar um conflito para quem já está designado ao projeto responde 409: redistribua antes. Conflito repetido também responde 409. Conflitos não são apagados.

**Distribuição.** Completa cada projeto até N avaliadores, priorizando quem tem menos
designações elegíveis no hackathon (desempate pelo id). A distribuição revalida as designações
vigentes e recompõe as vagas de avaliadores inelegíveis. Se faltarem avaliadores para qualquer
projeto, a operação inteira retorna 409 e a transação é revertida. A linha do hackathon fica
travada (`SELECT ... FOR UPDATE`) durante a operação.

**Redistribuição e auditoria.** O `PUT` recebe exatamente N ids distintos (422 caso contrário), todos elegíveis (409) e sem conflito com a equipe (409, com os ids no `detail`). Quem continua mantém a designação original. **Nada é apagado:** quem sai fica em `designacoes_projeto_final` com `removida_em` e `removida_por`. O índice parcial `uq_designacoes_projeto_final_vigente` impede duas designações vigentes iguais.

**Bloqueios.** Hackathon `FINALIZADO` ou `CANCELADO` bloqueia configurar, distribuir, redistribuir e registrar conflito (409).

**Pendente para a BE-S6-10.** A criação da avaliação deverá exigir submissão final válida e
designação elegível sem conflito. Na mesma trava do hackathon, a consulta de avaliações iniciadas
deverá alimentar `_projetos_com_avaliacao_iniciada`. A distribuição pula esses projetos e a
redistribuição responde 409 quando essa consulta informar que o projeto já iniciou a avaliação.

## Correções complementares da BE-S6-09 (PR #32)

As correções foram identificadas durante a revisão do PR #32 e incorporadas à implementação
da BE-S6-07 para consolidar a integração entre a submissão final e a avaliação técnica. Os
ajustes revalidam a elegibilidade dos avaliadores, reforçam a integridade referencial das
designações e dos conflitos de interesse e uniformizam o bloqueio de alterações em edições
encerradas. A implementação original da BE-S6-09 foi preservada, assim como o histórico de
designações e a separação entre avaliação científica e técnica.

### FIX 01 — Revalidar avaliadores técnicos

Antes, a distribuição contava todas as designações vigentes e a consulta individual
dependia apenas da designação. Agora, a distribuição e a consulta conferem perfil, situação e
estado da conta, organização e impedimentos RN13. Uma recomposição bem-sucedida registra data
e responsável de cada remoção. Se faltarem substitutos, as designações históricas e vigentes
permanecem como estavam. A correção afeta
[`services/designacao_projeto_final.py`](../app/services/designacao_projeto_final.py),
[`controllers/designacao_projeto_final.py`](../app/controllers/designacao_projeto_final.py)
e [`exceptions/projeto_final.py`](../app/exceptions/projeto_final.py).

### FIX 02 — Garantir a integridade das referências

Antes, cada chave estrangeira validava apenas a existência da referência. Agora, uma chave
composta obriga a designação a referenciar a combinação correta de proposta, equipe e edição.
Outra chave composta obriga a equipe do conflito a pertencer à edição informada. A migration
confere inclusive as designações removidas e falha com o identificador do primeiro registro
inconsistente. Os índices únicos e o histórico são preservados. A correção afeta
[`V202611251200`](../migrations/V202611251200__integridade_designacoes_projeto_final.sql),
[`models/designacao_projeto_final.py`](../app/models/designacao_projeto_final.py) e
[`models/submissao.py`](../app/models/submissao.py).

### FIX 03 — Bloquear alterações de configuração em edições encerradas

Antes, apenas o endpoint específico bloqueava alterações em edições encerradas. Agora, o
PATCH genérico retorna 409 se `avaliadores_por_projeto_final` muda e o estado atual ou o
estado solicitado é `FINALIZADO` ou `CANCELADO`. O bloqueio inclui limpar uma configuração
com `null` ou preencher uma configuração nula. Enviar o valor já persistido, inclusive
`null`, permite que o frontend continue enviando os demais campos na mesma requisição.
A correção afeta [`services/hackathon.py`](../app/services/hackathon.py),
[`views/hackathons.py`](../app/views/hackathons.py) e
[`services/designacao_projeto_final.py`](../app/services/designacao_projeto_final.py).
