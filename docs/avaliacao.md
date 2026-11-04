[← Voltar ao README](../README.md)

# Distribuição e avaliação científica — BE-S4-09 / BE-S4-10

RF29, RF30, RN11, RN12 e Q07 (2 a 3 avaliadores por proposta). Todas as rotas exigem token e conta ativa.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `PATCH /admin/hackathons/{id}/avaliacao/configuracao` | Organizador (e DEV) | Define `avaliadores_por_proposta` (2 ou 3) |
| `POST /admin/hackathons/{id}/avaliacoes/distribuir` | Organizador (e DEV) | Distribui as propostas `ENVIADA` entre os avaliadores |
| `PUT /admin/propostas/{submissao_id}/avaliadores` | Organizador (e DEV) | Redistribui uma proposta: troca os avaliadores pela lista `avaliador_ids` |
| `GET /admin/hackathons/{id}/avaliacoes/designacoes` | Organizador (e DEV) | Cada proposta `ENVIADA` com os avaliadores designados (lista vazia se ainda não distribuída) |
| `GET /avaliador/propostas` | Comitê Científico (e DEV) | Só as propostas designadas a quem está logado |
| `GET /avaliador/propostas/{submissao_id}` | Comitê Científico (e DEV) | Uma proposta designada a quem está logado; qualquer outra responde 404 |
| `GET /avaliador/propostas/{submissao_id}/avaliacao` | Comitê Científico (e DEV) | Sua própria avaliação, inclusive rascunho; 404 se ainda não existe |
| `PUT /avaliador/propostas/{submissao_id}/avaliacao/rascunho` | Comitê Científico (e DEV) | Cria ou substitui integralmente seu rascunho |
| `POST /avaliador/propostas/{submissao_id}/avaliacao/enviar` | Comitê Científico (e DEV) | Valida e envia sua avaliação definitiva e imutável |

**Onde fica o vínculo.** A tabela `designacoes_avaliacao` (`submissao_id`, `hackathon_id`, `avaliador_id`, `atribuido_por`, `atribuido_em`) guarda quem pode avaliar o quê, com `unique(submissao_id, avaliador_id)`. A avaliação fica em `avaliacoes` (BE-S4-10), cujo fluxo exige a designação antes de consultar ou gravar.

**Quantidade.** `hackathon.avaliadores_por_proposta` tem `CHECK` entre 2 e 3 e **não tem valor padrão**: fica `NULL` até o Organizador configurar, e distribuir ou redistribuir antes disso responde 409. Alterar a quantidade vale só para as próximas distribuições e **não mexe nas designações nem nas notas já existentes**: antes de iniciar a avaliação, uma proposta com mais ou menos avaliadores que o novo valor só muda se for redistribuída ou completada por uma nova distribuição (que nunca remove ninguém).

**Quem é avaliador.** `papel = COMITE_CIENTIFICO`, `ativo = true` e `situacao_conta = ATIVA`. O `DEV` não é elegível para distribuição, mas pode avaliar se já existir designação para ele, pela exceção administrativa adotada no projeto. Nas rotas `/avaliador/*`, inclusive para DEV, designação é obrigatória. **Limitação:** não existe vínculo avaliador-hackathon no banco, então vale todo avaliador elegível do sistema.

**Distribuição.** Só propostas `ENVIADA` entram; rascunhos ficam de fora. Cada proposta é completada até N avaliadores, sempre com quem tem menos propostas no hackathon (desempate pelo id, então o resultado é determinístico). Rodar de novo só completa o que falta e não altera propostas que já têm N ou mais avaliadores nem propostas com qualquer avaliação iniciada (inclusive rascunho sem nota final). Se faltar avaliador elegível para qualquer proposta, a resposta é 409 e **nada é gravado**. A resposta traz `propostas_distribuidas`, `designacoes_criadas` e `propostas_ja_completas`.

**Redistribuição (manual, por proposta).** O `PUT` recebe exatamente N ids distintos (422 se a quantidade for outra ou houver repetidos) e todos precisam ser elegíveis (409 caso contrário). Quem continua na lista mantém a designação original. Não há modo automático de redistribuição.

**Antes de a avaliação começar.** Distribuir e redistribuir respondem 409 quando `hackathon.status` é `EM_AVALIACAO`, `FINALIZADO` ou `CANCELADO`. Redistribuir também responde 409 se já existir qualquer registro em `avaliacoes`, inclusive rascunho com `nota = NULL`, ou se a proposta não estiver `ENVIADA`. A distribuição automática ignora propostas com avaliação iniciada.

**Concorrência.** As duas operações travam a linha do `hackathon` (`SELECT ... FOR UPDATE`) e conferem a contagem dentro do service, então duas distribuições simultâneas não duplicam designações.

**Isolamento.** `GET /avaliador/propostas` filtra por `usuario.id`. Proposta de outro avaliador ou inexistente responde 404 com a mesma mensagem, sem revelar que existe. A resposta ao avaliador não traz `equipe_id`, para não expor quem escreveu a proposta.

**Erros.** 401 (sem token ou token inválido), 403 (perfil sem permissão ou conta pendente), 404 (hackathon ou proposta inexistente, ou proposta não designada ao avaliador), 409 (quantidade não configurada, avaliação já iniciada, proposta com nota ou não enviada, avaliadores insuficientes ou não elegíveis) e 422 (quantidade fora de 2 a 3, lista de tamanho errado ou com repetidos). Os detalhes de cada rota estão no Swagger.

## Avaliação pela rubrica (RF30, RN11, RN12)

Só o Comitê Científico ou DEV com designação pode salvar, enviar ou consultar sua própria avaliação. Outros avaliadores da mesma proposta não têm acesso ao seu conteúdo. O backend identifica o avaliador pelo token; não aceita `avaliador_id`, `rubrica_id`, `status` ou `nota_final` no corpo. A proposta precisa estar `ENVIADA` e ter rubrica publicada da mesma edição (409 caso contrário).

Exemplo de corpo para salvar rascunho ou enviar diretamente:

```json
{
  "notas": [
    {"criterio_id": "00000000-0000-0000-0000-000000000001", "nota": "7.35"},
    {"criterio_id": "00000000-0000-0000-0000-000000000002", "nota": "4"}
  ],
  "parecer": "Método consistente e viabilidade demonstrada na proposta.",
  "recomendacao": "APROVACAO"
}
```

`PUT .../rascunho` substitui integralmente o conteúdo: aceita `{}`, notas incompletas e parecer/recomendação nulos. Campos omitidos são limpos; não é um PATCH. Mesmo no rascunho, cada nota deve ser finita, estar na escala inclusiva de seu critério e pertencer à rubrica da proposta. Critérios repetidos, inexistentes ou de outra rubrica retornam 422. `nota_final` permanece nula até o envio.

`POST .../enviar` sem corpo (ou com `null`) envia o rascunho persistido; sem avaliação salva, responde 404. Com corpo, valida e envia aquele conteúdo integralmente, podendo criar a avaliação diretamente. Exige nota em todos os critérios, parecer com texto além de espaços e recomendação `APROVACAO` ou `REPROVACAO` (422 se faltar). Atualiza `status = ENVIADA`, `avaliado_em` e `atualizado_em` em UTC e calcula a nota no servidor. Edição ou reenvio de avaliação enviada retorna 409.

`GET .../avaliacao` retorna `id`, `submissao_id`, `avaliador_id`, `rubrica_id`, `status`, `nota_final`, `notas`, `parecer`, `recomendacao`, `atualizado_em` e `avaliado_em`. Decimais são serializados como strings. Antes do primeiro salvamento responde 404. Não existe endpoint para consultar a avaliação de outra pessoa.

### Nota ponderada

```text
nota_normalizada = 10 × (nota − escala_min) / (escala_max − escala_min)
nota_final = soma(nota_normalizada × peso / 100)
```

Usa `Decimal` com precisão intermediária de 50 dígitos, pesos percentuais e arredondamento `ROUND_HALF_UP` somente no total, para duas casas decimais. Por exemplo, nota 7,35 na escala 0–10 com peso 60% e nota 4 na escala 1–5 com peso 40% resultam em **7,41**. O cliente deve enviar decimais como strings para preservar a precisão.

**Hipótese pendente:** a normalização da nota final para 0–10 e a convenção de arredondamento precisam ser validadas com o Squad 1; não há decisão oficial registrada neste repositório. A média entre avaliadores, consenso, homologação pelo organizador e publicação dos resultados dependem da Q07 e pertencem à BE-S4-11. Até lá, notas, recomendações e pareceres não aparecem no painel nem na consulta de proposta da equipe.

### Persistência e concorrência

A migration `V202611031800__avaliacao_cientifica.sql` evolui `avaliacoes` com `status`, `rubrica_id`, `recomendacao` e `atualizado_em`. O parecer reutiliza `comentarios`; a nota final reutiliza `nota`. `notas_criterio_avaliacao` guarda as notas individuais, com unicidade `(avaliacao_id, criterio_id)`; `avaliacoes` passa a exigir unicidade `(submissao_id, avaliador_id)`.

Avaliações legadas com nota ou data de avaliação tornam-se `ENVIADA`, preservando integralmente notas, comentários e datas; não se inventam rubrica, notas por critério ou recomendação para esses registros. Linhas legadas sem nota e sem data ficam `RASCUNHO`. Se houver pares proposta/avaliador duplicados, a migration falha antes de alterar a estrutura, com `avaliacoes_duplicadas`: é necessário conciliar esses dados explicitamente, sem exclusão automática. Para identificar:

```sql
SELECT submissao_id, avaliador_id, count(*)
FROM avaliacoes
GROUP BY submissao_id, avaliador_id
HAVING count(*) > 1;
```

Salvamento e envio usam uma transação, sempre bloqueando `hackathon` antes de `submissao`, compatível com a distribuição da BE-S4-09. Revalidam a designação após obter o bloqueio. O bloqueio do hackathon também protege a primeira avaliação, quando ainda não existe uma linha para bloquear. Dois envios simultâneos produzem um sucesso e um 409; falhas desfazem a avaliação e suas notas. A rubrica publicada permanece imutável pela BE-S4-06.

Os testes aplicam os scripts reais em schemas temporários para validar banco vazio, atualização com dados legados e rejeição de duplicatas. O Compose monta `migrations` em `/code/migrations` somente para leitura, permitindo essa validação dentro do container de desenvolvimento.

---

[← Voltar ao README](../README.md)
