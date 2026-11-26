[← Voltar ao README](../README.md)

# Feedbacks do mentor e histórico da mentoria — BE-S6-03

O mentor registra feedbacks para as equipes que acompanha (RF40). As equipes, o mentor e os
gestores consultam esses feedbacks e uma linha do tempo que junta entregas e feedbacks (RF42).
Valem a atribuição vigente (RN16) e o calendário de [entregas](mentoria-entregas.md). As rotas
ficam na seção **Feedbacks da mentoria** do `/docs` e exigem JWT de conta ativa.

## Rotas

| Método | Caminho | Sucesso | Quem pode acessar |
| --- | --- | --- | --- |
| POST | `/equipes/{equipe_id}/mentoria/feedbacks` | 201 (200 na repetição da `Idempotency-Key`) | Mentor com atribuição vigente na equipe, DEV |
| GET | `/equipes/{equipe_id}/mentoria/feedbacks` | 200 | Integrantes da equipe, mentor vigente, gestores da organização dona da edição, DEV |
| GET | `/equipes/{equipe_id}/mentoria/historico` | 200 | Mesmos acessos da listagem |

As duas consultas aceitam `limite` de 1 a 100 (padrão 50) e `deslocamento` a partir de 0 e
ordenam do mais recente ao mais antigo. A leitura continua disponível com a edição encerrada.
Não existe `GET /me/mentoria/feedbacks`: o [painel do mentor](painel-mentor.md) cobre a visão do mentor.

| Código | Quando |
| --- | --- |
| 401 | Sem JWT, JWT inválido ou conta desativada |
| 403 | Escrita por perfil diferente de Mentor (e DEV): participante, avaliador, gestor |
| 404 | Equipe inexistente, de outra organização ou fora do escopo. É o mesmo 404 nos três casos |
| 409 | Equipe inelegível, edição `FINALIZADO` ou `CANCELADO`, feedback já corrigido, `Idempotency-Key` com outro conteúdo, equipe sem mentor vigente (só DEV) |
| 422 | Payload inválido, entrega ou marco fora da equipe e da edição, correção inválida |

Diferente das rotas de entregas, que respondem 403 fora do escopo, as rotas de feedback respondem
404 para não confirmar que a equipe existe.

## Escrever um feedback

```json
{
  "texto": "Priorizem o fluxo de cadastro antes do próximo marco.",
  "status_acompanhamento": "ATENCAO",
  "marco_id": "4f870fb8-5957-4bb4-8075-ca8371297c75",
  "entrega_id": null,
  "corrige_id": null
}
```

- `texto`: de 1 a 5.000 caracteres, sem espaços nas pontas.
- `status_acompanhamento`: `NO_RITMO`, `ATENCAO`, `EM_RISCO` ou `CONCLUIDO` (lista provisória).
- `marco_id` e `entrega_id` são opcionais. Sem os dois, o feedback é geral. Com só `entrega_id`,
  o marco é o da entrega. Com os dois, o marco precisa ser o da entrega, senão 422. O marco
  precisa ser da edição da equipe e a entrega, da própria equipe.
- O autor vem sempre do JWT. Campos desconhecidos dão 422.
- A resposta não traz `atribuicao_id` nem o id do autor, só `autor_nome`.

O feedback é gravado com o vínculo do mentor naquele momento. Um mentor substituído ou com o
vínculo encerrado perde leitura e escrita na consulta seguinte. O mentor novo lê todo o histórico
da equipe, inclusive os feedbacks do anterior, que aparecem só com o nome do autor.

### Elegibilidade

A equipe precisa estar homologada, com proposta aprovada no resultado (`equipe_aprovada`), e a
edição não pode estar `FINALIZADO` ou `CANCELADO`. DEV também precisa de um mentor vigente na
equipe, porque o feedback registra o vínculo.

## Imutabilidade e correção

A tabela `feedbacks_mentoria` é só de inserção. A API não tem `PUT`, `PATCH` nem `DELETE`, e um
trigger do banco recusa `UPDATE` e `DELETE`. Para corrigir um feedback, envie um novo com
`corrige_id`:

```json
{
  "texto": "Versão corrigida do feedback.",
  "status_acompanhamento": "NO_RITMO",
  "corrige_id": "0b0cfc3e-6f15-4e0c-bb9c-4c5b4a0b9a11"
}
```

- O original nunca muda. Na listagem ele ganha `corrigido_por_id` com o id da correção.
- O feedback a corrigir precisa ser da mesma equipe e do mesmo autor (422 caso contrário).
- Cada feedback é corrigido no máximo uma vez. A segunda tentativa, inclusive simultânea, dá 409
  (índice único parcial em `corrige_id`). Dá para corrigir uma correção.
- O mentor novo **não** corrige o feedback de outro mentor: escreve um feedback novo.

## Idempotência

O cabeçalho opcional `Idempotency-Key` (1 a 128 caracteres) protege contra reenvio por falha de
rede. A chave vale por autor.

| Situação | Resposta |
| --- | --- |
| Sem chave | Cada pedido cria um feedback |
| Mesma chave e mesmo conteúdo | `200` com o feedback já criado, sem duplicar nem notificar de novo |
| Mesma chave e conteúdo diferente | `409` |
| Chaves diferentes | Dois feedbacks |

## Histórico da mentoria

`GET /equipes/{equipe_id}/mentoria/historico` devolve uma união discriminada por `tipo`. Cada item
tem `tipo`, `ocorrido_em` (envio da entrega ou criação do feedback, em UTC) e o objeto do tipo:

```json
[
  {
    "tipo": "FEEDBACK",
    "ocorrido_em": "2026-11-26T12:00:00Z",
    "feedback": {
      "id": "0b0cfc3e-6f15-4e0c-bb9c-4c5b4a0b9a11",
      "equipe_id": "6a8f3f0a-5d5e-4a38-9d0c-0d5a2f6d3a10",
      "hackathon_id": "c9e3f6a2-1c3b-4f0e-8a58-2c2f0f3d9a77",
      "marco_id": null,
      "entrega_id": null,
      "autor_nome": "Mentora Ana",
      "status_acompanhamento": "ATENCAO",
      "texto": "Priorizem o fluxo de cadastro.",
      "criado_em": "2026-11-26T12:00:00Z",
      "corrige_id": null,
      "corrigido_por_id": null
    }
  },
  {
    "tipo": "ENTREGA",
    "ocorrido_em": "2026-11-20T15:30:00Z",
    "entrega": {
      "id": "4d7c6a5e-9b2f-4b6a-8e1d-3f6a7c8b9d01",
      "marco_id": "4f870fb8-5957-4bb4-8075-ca8371297c75",
      "equipe_id": "6a8f3f0a-5d5e-4a38-9d0c-0d5a2f6d3a10",
      "hackathon_id": "c9e3f6a2-1c3b-4f0e-8a58-2c2f0f3d9a77",
      "enviado_por": "2c1b6a79-3e0a-4a7c-9d77-8a1b2c3d4e5f",
      "enviado_em": "2026-11-20T15:30:00Z",
      "data_limite_no_envio": "2026-11-21T02:59:00Z",
      "descricao": "Implementamos os fluxos de cadastro e consulta.",
      "referencias": ["https://github.com/equipe/prototipo"]
    }
  }
]
```

O objeto `entrega` é o mesmo schema de `GET /equipes/{equipe_id}/mentoria/entregas`. A união é uma
consulta `UNION ALL` ordenada por `ocorrido_em` decrescente e `id`, com `LIMIT` e `OFFSET` no banco.
O banco devolve só o tipo e o id de cada posição, e duas consultas por `id` completam os dados
(constante, sem N+1). Uma equipe sem entregas recebe só feedbacks, e sem nada recebe `[]`.

A [submissão final](submissao-final.md) (BE-S6-07) **não** entra no histórico: ela é uma entrega do
marco `FINAL` com relatório e repositório próprios, e a listagem de entregas já a omite. Os dados
dela têm a consulta própria `GET /equipes/{equipe_id}/mentoria/submissao-final`. Como o filtro é o
mesmo, nenhum item do histórico expõe artefatos finais. Um feedback pode referenciar o marco `FINAL`.

## Notificação

Cada feedback novo cria um aviso in-app do tipo `MENTOR` na [central](central-de-notificacoes.md),
na mesma transação, dentro de um savepoint: se o aviso falhar, o feedback é gravado mesmo assim.

- Destinatários: integrantes confirmados da equipe. Convites pendentes e o autor ficam de fora.
- Chave `feedback_mentoria:{feedback_id}`, `referencia_tipo = FEEDBACK_MENTORIA` e
  `referencia_id` igual ao id do feedback.
- `dados` traz só `equipe_id` e `status_acompanhamento`. O texto não vai no aviso.
- Nenhum e-mail entra na fila.

## Banco de dados

[Migration V202611261100](../migrations/V202611261100__feedbacks_mentoria.sql). Decisões de modelagem:

- Chaves compostas garantem que equipe e marco sejam da mesma edição, que a entrega seja da mesma
  equipe e do mesmo marco, e que a correção seja da mesma equipe e do mesmo autor. A restrição
  `uq_entregas_mentoria_vinculo` (já existente) cobre a entrega, sem criar outra restrição
  `UNIQUE (id, equipe_id)`.
- `status_acompanhamento` é `varchar` com `CHECK`, e não enum do PostgreSQL, para trocar a lista
  sem migrar um tipo.
- Índices: `(equipe_id, criado_em DESC, id)`, parciais em `entrega_id` e `marco_id`, e único parcial
  em `corrige_id`. A idempotência usa `UNIQUE (autor_id, chave_idempotencia)`.
- As chaves estrangeiras **não** têm `ON DELETE CASCADE`: apagar equipe, usuário, atribuição ou
  marco que tenha feedback falha. Assim o trigger de imutabilidade não conflita com cascatas, e
  nenhum fluxo da API apaga esses registros (a exclusão de marco com feedbacks retorna 409).
- O trigger é `BEFORE UPDATE OR DELETE ... FOR EACH ROW`, e não age sobre `TRUNCATE`. Os testes
  limpam os feedbacks com `session_replication_role = replica` numa sessão própria.

## Decisões pendentes

- **Lista de status.** `NO_RITMO`, `ATENCAO`, `EM_RISCO` e `CONCLUIDO` são provisórios e dependem
  de validação do grupo. Como há `CHECK` e não enum, trocar é uma migration pequena.
- **Q24, visibilidade do mentor.** Sem decisão. Está implementada a regra restritiva: o mentor com
  vínculo vigente lê só as equipes atuais, com o histórico completo delas. Ampliar a visibilidade
  exige a validação da Q24.
- **E-mail para feedback.** O aviso é só in-app. Enviar e-mail depende de decisão sobre texto,
  frequência e privacidade (o texto do feedback não deve ir para a caixa de e-mail).
- **Corrigir o feedback de outro mentor.** Está proibido: o mentor novo escreve um feedback novo.
  Se o grupo decidir o contrário, é preciso rever a regra de mesmo autor na correção.
- **Erro ao corrigir feedback alheio.** Hoje responde 422, e não 403 ou 409.

## Testes

[`tests/test_feedbacks_mentoria.py`](../tests/test_feedbacks_mentoria.py) cobre permissões por
perfil, o 404 igual para equipe inexistente e fora do escopo, mentor substituído, edição encerrada,
equipe inelegível, duas organizações, paginação e ordem com empate, trigger, correção (inclusive
simultânea), vínculos inconsistentes, idempotência (inclusive simultânea), notificação, painel e
histórico.
