# Calendário e entregas parciais da mentoria

O Comitê Científico configura os prazos comuns às equipes de uma edição (RF65, RN17 e RN29).
O líder técnico registra as entregas parciais dentro desses prazos (RF39). A elegibilidade
reaproveita a inscrição homologada e o resultado da proposta usado na
[atribuição de mentores](atribuicao-mentores.md) (RF38). Os envios são a parte de entregas do
histórico previsto pelo RF42. Os registros e feedbacks feitos pelo mentor (RF40) entram na
BE-S6-03. O RF44 vincula a futura submissão final ao último marco.
[Documento de Requisitos da Sprint 4](https://drive.google.com/file/d/1-9XQhZlE_ZbIGoY6Sw8Qb_a2PEcQ3d-Z/view)

## Modelagem

| Tabela | Campos e restrições |
| --- | --- |
| `marcos_mentoria` | UUID, edição, título, descrição, prazo, ordem, tipo `PARCIAL` ou `FINAL` e datas de criação e atualização. O índice do calendário segue edição, prazo, ordem e UUID. Um índice único parcial admite até um marco `FINAL` por edição. |
| `entregas_mentoria` | UUID, marco, equipe, edição, usuário autor, data de envio, prazo vigente no envio, descrição e array de referências HTTPS. As chaves estrangeiras compostas garantem que equipe e marco sejam da própria edição. O par marco–equipe é único. O banco exige envio até o prazo registrado e protege o histórico contra exclusão do marco. |

As datas novas usam `timestamptz` e a API as devolve em UTC. As tabelas são criadas pela
[migration V202611251000](../migrations/V202611251000__marcos_e_entregas_mentoria.sql).

## Contratos no Swagger

As rotas ficam na seção **Entregas da mentoria** do `/docs` e exigem JWT de conta ativa.

| Método | Caminho | Sucesso | Quem pode acessar |
| --- | --- | --- | --- |
| POST | `/admin/hackathons/{hackathon_id}/mentoria/marcos` | 201 | Comitê Científico e Organizador da organização proprietária, DEV |
| GET | `/admin/hackathons/{hackathon_id}/mentoria/marcos` | 200 | Mesmos gestores |
| GET | `/admin/hackathons/{hackathon_id}/mentoria/marcos/{marco_id}` | 200 | Mesmos gestores |
| PATCH | `/admin/hackathons/{hackathon_id}/mentoria/marcos/{marco_id}` | 200 | Mesmos gestores |
| DELETE | `/admin/hackathons/{hackathon_id}/mentoria/marcos/{marco_id}` | 204 | Mesmos gestores |
| GET | `/hackathons/{hackathon_id}/mentoria/marcos` | 200 | Integrantes de equipes homologadas com proposta aprovada, mentores com atribuição vigente na edição e gestores autorizados |
| POST | `/equipes/{equipe_id}/mentoria/entregas` | 201 | Líder técnico da equipe e DEV |
| GET | `/equipes/{equipe_id}/mentoria/entregas` | 200 | Integrantes da equipe, mentor vigente da equipe e gestores autorizados |
| GET | `/equipes/{equipe_id}/mentoria/entregas/{entrega_id}` | 200 | Mesmas permissões da listagem |

As listagens aceitam `limite` de 1 a 100 (padrão 50) e `deslocamento` a partir de 0 (padrão 0).
Os erros seguem o campo `detail` da API. `401` indica autenticação inválida ou conta
desativada, `403` indica conta pendente ou autorização insuficiente, `404` indica recurso
ausente no caminho ou edição privada, `409` indica conflito de calendário, elegibilidade,
prazo, tipo ou registro duplicado e `422` indica dados inválidos.

## Cadastro e consulta de marcos

1. O gestor envia título, descrição, prazo e, opcionalmente, ordem e tipo.
2. O prazo deve estar entre o início e o fim da edição, quando definidos. Também deve ser
   igual ou posterior ao encerramento das propostas e à conclusão do treinamento, se essas
   datas já estiverem registradas. Datas com fuso são convertidas para UTC e datas sem
   fuso são interpretadas como UTC.
3. O calendário ordena pelo prazo, depois pela ordem configurada e, em caso de empate,
   pelo UUID. Se houver um marco `FINAL`, a combinação prazo e ordem dele precisa vir após
   todos os parciais. No mesmo prazo, o final precisa de uma ordem maior.
4. O gestor pode aplicar um PATCH com os campos que deseja alterar. O prazo registrado
   em cada envio permanece disponível após ajustes de calendário. Marcos com entregas já
   registradas mantêm seu tipo e ficam protegidos contra exclusão.

Exemplo de criação de um marco parcial

```json
{
  "titulo": "Protótipo navegável",
  "descricao": "Descreva o fluxo principal e o que já funciona.",
  "data_limite": "2026-12-08T20:59:00-03:00",
  "ordem": 1,
  "tipo": "PARCIAL"
}
```

## Registro e consulta de entregas

1. O líder envia um `marco_id` da edição da equipe, uma `descricao` e, quando tiver
   material externo, `referencias`. As referências usam a política de links HTTPS do
   projeto, com até 2.048 caracteres por URL.
2. A API exige equipe homologada, proposta aprovada no resultado da edição, treinamento
   concluído e edição aberta para mentoria. O envio é permitido até o instante do prazo,
   inclusive. Se as datas da edição mudarem, um prazo que entrou em conflito com o calendário
   precisa ser ajustado para voltar a aceitar envios.
3. O servidor grava autor e horário, deriva equipe e edição do caminho e guarda o prazo
   vigente no envio. A restrição única do banco impede envios duplicados, inclusive
   simultâneos.
4. As duas rotas de consulta por equipe mostram os registros autorizados, com o mais
   recente primeiro na listagem. A substituição ou o encerramento da atribuição encerra
   o acesso do mentor anterior. O mentor vigente pode consultar os envios anteriores da
   equipe que passou a acompanhar.

Exemplo de envio de uma entrega parcial

```json
{
  "marco_id": "4f870fb8-5957-4bb4-8075-ca8371297c75",
  "descricao": "Implementamos os fluxos de cadastro e consulta.",
  "referencias": ["https://github.com/equipe/prototipo"]
}
```

## Decisões pendentes e integração

- **Reenvio parcial.** Até existir uma política de substituição, vale um registro
  imutável por equipe e marco. Uma segunda tentativa dentro do prazo retorna `409`.
- **Cronograma (Q11).** Cada edição define a quantidade e as datas. O backend usa os
  limites disponíveis da edição e o registro de conclusão do treinamento como referência
  para o início da mentoria. A BE-S7-05 poderá usar uma fase própria quando houver
  abertura e encerramento de fases no calendário.
- **Feedback e painel (BE-S6-03 e BE-S6-04).** O UUID da entrega permite associar
  feedbacks. Marco, equipe, data e atribuição vigente fornecem os dados para a linha
  do tempo e o acompanhamento de pendências.
- **Submissão final e versões (BE-S6-07 e BE-S6-08).** O marco `FINAL` fica reservado
  para o fluxo de envio final. Ele pode usar a mesma entidade de entrega por equipe e
  marco. As versões futuras podem apontar para essa entrega, mantendo sua identidade
  e registrando versões dos materiais e dos protocolos. Os requisitos específicos de
  repositório e relatório serão tratados nesse fluxo (RF44, Q13).
