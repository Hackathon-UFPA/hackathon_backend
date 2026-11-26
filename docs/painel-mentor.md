[← Voltar ao README](../README.md)

# Painel do mentor — BE-S6-04

Acompanhamento das equipes designadas ao mentor: progresso nos marcos, entregas e pendências
(RF41, RF39, RF42, RN16). As rotas são somente de leitura e ficam na seção **Painel do mentor**
do `/docs`. Não há tabela nova: o painel lê as [atribuições](atribuicao-mentores.md) e o
[calendário e as entregas](mentoria-entregas.md).

## Rotas

| Método | Caminho | O que devolve |
| --- | --- | --- |
| GET | `/me/mentoria/painel` | Equipes acompanhadas, com progresso, próximo marco e resumo geral |
| GET | `/me/mentoria/painel/equipes/{equipe_id}` | Os mesmos dados da equipe, mais integrantes, calendário e entregas |

Exigem JWT de Mentor com a ativação concluída (RN33). Nenhuma rota recebe o id de um mentor: o
painel é sempre o de quem está autenticado. DEV passa na checagem de perfil, como no restante da
API, mas só recebe vínculos da própria conta.

A lista aceita os filtros `hackathon_id` e `equipe_id`, além de `limite` (1 a 100, padrão 50) e
`deslocamento` (a partir de 0). A ordem é nome da edição, nome da equipe e id. `total` conta as
equipes filtradas, e `resumo` soma **todas** elas, não só as da página.

## Quem aparece no painel

Uma equipe só aparece quando atende a todas as condições:

1. Tem atribuição **vigente** para o mentor autenticado (`encerrada_em IS NULL`).
2. Está `HOMOLOGADA`.
3. Tem proposta aprovada no resultado homologado da própria edição.
4. A edição é da organização do mentor.

Quando o mentor é substituído, o vínculo é encerrado ou a equipe deixa de atender a alguma
condição, o acesso acaba na consulta seguinte. O novo mentor vê as entregas anteriores.

No detalhe, uma equipe inexistente e uma equipe fora do escopo recebem o **mesmo 404**. Na lista,
um filtro fora do escopo devolve zero equipes. Assim a API não confirma que o recurso existe.

| Código | Quando |
| --- | --- |
| 401 | Sem JWT, JWT inválido ou conta desativada |
| 403 | Perfil diferente de Mentor (ou DEV) ou mentor sem a ativação concluída |
| 404 | Detalhe de equipe inexistente ou fora do acompanhamento vigente |
| 422 | Filtro ou paginação inválidos |

## Dados expostos

Dos integrantes saem apenas **nome e função**. O painel não devolve e-mails, ids de usuários,
instituição, comprovantes, notas, pareceres, classificação, motivos administrativos nem
conversas. Das entregas saem id, data de envio, prazo vigente no envio, descrição e referências,
sem o autor.

## Progresso e pendências

A situação é calculada na hora da consulta:

| Situação | Regra |
| --- | --- |
| `ENTREGUE` | A equipe tem entrega registrada no marco |
| `PENDENTE` | Sem entrega, prazo ainda não vencido (inclusivo) e edição aberta |
| `NAO_ENTREGUE` | Sem entrega e com prazo vencido, ou edição `FINALIZADO` ou `CANCELADO` |

- `progresso` e `resumo` contam só os marcos **parciais**. O envio do marco `FINAL` pertence à
  submissão final (BE-S6-07): ele aparece no detalhe com `situacao` nula enquanto não houver
  entrega, para não ser apontado como atraso antes de existir o fluxo de envio.
- `proximo_marco` é o marco pendente de prazo mais próximo, ou nulo.
- `equipes_com_nao_entregues` conta as equipes com ao menos um marco `NAO_ENTREGUE`.
- `PENDENTE` indica que o prazo está aberto. O envio ainda segue as validações de
  [registro de entrega](mentoria-entregas.md#registro-e-consulta-de-entregas).

## Feedbacks no painel (BE-S6-03)

Só campos aditivos: os campos anteriores não mudaram.

| Onde | Campo | Conteúdo |
| --- | --- | --- |
| Cada equipe | `ultimo_feedback` | `{id, criado_em, status_acompanhamento}` do feedback mais recente de qualquer mentor, ou `null` |
| Cada equipe | `dias_sem_feedback` | Dias inteiros (UTC) desde o último feedback, ou `null` se nunca houve |
| `resumo` | `equipes_sem_feedback` | Equipes filtradas que nunca receberam feedback |
| Detalhe | `feedbacks_recentes` | Até 5 feedbacks, com `trecho` de até 140 caracteres e sem o texto completo |

O texto completo está em `GET /equipes/{equipe_id}/mentoria/feedbacks`. O último feedback vem de
uma consulta agrupada (`DISTINCT ON` por equipe), sem N+1.

## Consultas

A lista usa quatro consultas, qualquer que seja a quantidade de equipes
([controller](../app/controllers/painel_mentor.py)):

1. Equipes autorizadas, em uma consulta que junta atribuições, equipes e edições e aplica as
   quatro condições de visibilidade (índice `ix_atribuicoes_mentor_vigentes`).
2. Marcos das edições dessas equipes (índice `ix_marcos_mentoria_calendario`).
3. Entregas dessas equipes (índice `ix_entregas_mentoria_equipe_historico`).
4. Último feedback de cada equipe (índice `ix_feedbacks_mentoria_equipe`).

O detalhe acrescenta uma consulta de integrantes. A paginação é aplicada depois da agregação,
porque o resumo precisa de todas as equipes. A quantidade de vínculos vigentes é limitada pela
capacidade do mentor (`max_equipes`).

## Decisões pendentes e próximos passos

- **Q24, visibilidade de outras equipes.** Ainda sem decisão. Vale a alternativa restritiva: o
  mentor só vê as equipes que acompanha. Ampliar o acesso exige a validação da Q24.
- **Sessões individuais de mentoria.** A atualização de escopo de 19/11 pede sessões no painel
  quando a modelagem da BE-S6-01 estiver pronta. Elas ainda não estão modeladas, por isso o
  painel não as traz, nem o estado de sessão cancelada.
- **Feedbacks (BE-S6-03).** Os campos de feedback do painel estão na seção seguinte. As
  decisões pendentes de status, Q24, e-mail e correção estão em
  [Feedbacks do mentor](feedbacks-mentoria.md#decisões-pendentes).
- **Chat (BE-S6-05).** Fica fora deste card.
- **Contrato com o frontend.** Precisa de revisão com o time de frontend.

## Testes

[`tests/test_painel_mentor.py`](../tests/test_painel_mentor.py) cobre a agregação, filtros e
paginação, edição encerrada, ausência de dados sensíveis, mentor substituído ou encerrado, equipe
não homologada ou reprovada, isolamento entre organizações, autorização negativa e a fronteira
do prazo.

```sh
docker compose run --rm flyway_test
docker compose run --rm --no-deps app python -m pytest tests/test_painel_mentor.py
```
