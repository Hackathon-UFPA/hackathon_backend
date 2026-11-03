# Distribuição de propostas aos avaliadores — BE-S4-09

RF29 e Q07 (2 a 3 avaliadores por proposta). Todas as rotas exigem token e conta ativa.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `PATCH /admin/hackathons/{id}/avaliacao/configuracao` | Organizador (e DEV) | Define `avaliadores_por_proposta` (2 ou 3) |
| `POST /admin/hackathons/{id}/avaliacoes/distribuir` | Organizador (e DEV) | Distribui as propostas `ENVIADA` entre os avaliadores |
| `PUT /admin/propostas/{submissao_id}/avaliadores` | Organizador (e DEV) | Redistribui uma proposta: troca os avaliadores pela lista `avaliador_ids` |
| `GET /admin/hackathons/{id}/avaliacoes/designacoes` | Organizador (e DEV) | Cada proposta `ENVIADA` com os avaliadores designados (lista vazia se ainda não distribuída) |
| `GET /avaliador/propostas` | Comitê Científico (e DEV) | Só as propostas designadas a quem está logado |
| `GET /avaliador/propostas/{submissao_id}` | Comitê Científico (e DEV) | Uma proposta designada a quem está logado; qualquer outra responde 404 |

**Onde fica o vínculo.** A tabela `designacoes_avaliacao` (`submissao_id`, `hackathon_id`, `avaliador_id`, `atribuido_por`, `atribuido_em`) guarda quem pode avaliar o quê, com `unique(submissao_id, avaliador_id)`. A nota continua em `avaliacoes` (BE-S4-10): ela pode conferir a designação antes de gravar a nota.

**Quantidade.** `hackathon.avaliadores_por_proposta` tem `CHECK` entre 2 e 3 e **não tem valor padrão**: fica `NULL` até o Organizador configurar, e distribuir ou redistribuir antes disso responde 409. Alterar a quantidade vale só para as próximas distribuições e **não mexe nas designações nem nas notas já existentes**: uma proposta com mais ou menos avaliadores que o novo valor só muda se for redistribuída ou completada por uma nova distribuição (que nunca remove ninguém).

**Quem é avaliador.** `papel = COMITE_CIENTIFICO`, `ativo = true` e `situacao_conta = ATIVA`. O `DEV` não pode ser avaliador, mas pode usar todas as rotas; nas rotas `/avaliador/*` ele vê só o que foi designado a ele, como os demais. **Limitação:** não existe vínculo avaliador-hackathon no banco, então vale todo avaliador elegível do sistema.

**Distribuição.** Só propostas `ENVIADA` entram; rascunhos ficam de fora. Cada proposta é completada até N avaliadores, sempre com quem tem menos propostas no hackathon (desempate pelo id, então o resultado é determinístico). Rodar de novo só completa o que falta e não altera propostas que já têm N ou mais avaliadores nem propostas que já têm nota. Se faltar avaliador elegível para qualquer proposta, a resposta é 409 e **nada é gravado**. A resposta traz `propostas_distribuidas`, `designacoes_criadas` e `propostas_ja_completas`.

**Redistribuição (manual, por proposta).** O `PUT` recebe exatamente N ids distintos (422 se a quantidade for outra ou houver repetidos) e todos precisam ser elegíveis (409 caso contrário). Quem continua na lista mantém a designação original. Não há modo automático de redistribuição.

**Antes de a avaliação começar.** Distribuir e redistribuir respondem 409 quando `hackathon.status` é `EM_AVALIACAO`, `FINALIZADO` ou `CANCELADO`, ou quando a proposta já tem alguma nota em `avaliacoes`. Redistribuir uma proposta que não está `ENVIADA` também dá 409.

**Concorrência.** As duas operações travam a linha do `hackathon` (`SELECT ... FOR UPDATE`) e conferem a contagem dentro do service, então duas distribuições simultâneas não duplicam designações.

**Isolamento.** `GET /avaliador/propostas` filtra por `usuario.id`. Proposta de outro avaliador ou inexistente responde 404 com a mesma mensagem, sem revelar que existe. A resposta ao avaliador não traz `equipe_id`, para não expor quem escreveu a proposta.

**Erros.** 401 (sem token ou token inválido), 403 (perfil sem permissão ou conta pendente), 404 (hackathon ou proposta inexistente, ou proposta não designada ao avaliador), 409 (quantidade não configurada, avaliação já iniciada, proposta com nota ou não enviada, avaliadores insuficientes ou não elegíveis) e 422 (quantidade fora de 2 a 3, lista de tamanho errado ou com repetidos). Os detalhes de cada rota estão no Swagger.
