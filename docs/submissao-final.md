# Submissão final da mentoria — BE-S6-07

O RF44 define a submissão final como a última entrega do calendário comum da mentoria (RF65
e RN17). O backend registra a entrega em `entregas_mentoria`, usando o marco `FINAL` cadastrado
para a edição. O campo `id` identifica a entrega. O campo `submissao_id` identifica a proposta
científica aprovada no resultado homologado e é o mesmo usado na avaliação técnica.
Consulte o [Documento de Requisitos](https://drive.google.com/file/d/1-9XQhZlE_ZbIGoY6Sw8Qb_a2PEcQ3d-Z/view).

## Contrato da API

As rotas exigem JWT de conta ativa e estão disponíveis no Swagger (`/docs`).

| Método | Caminho | Sucesso | Permissão |
| --- | --- | --- | --- |
| POST | `/equipes/{equipe_id}/mentoria/submissao-final` | 201 com a submissão registrada | Líder técnico da equipe ou DEV |
| GET | `/equipes/{equipe_id}/mentoria/submissao-final` | 200 com a submissão registrada | Integrantes da equipe, mentor vigente, Comitê Científico e Organizador da organização proprietária, ou DEV |
| GET | `/equipes/{equipe_id}/mentoria/submissao-final/relatorio` | 200 com o PDF em anexo | Mesmas permissões da consulta da submissão |
| GET | `/comite-tecnico/projetos-finais/{submissao_id}/relatorio` | 200 com o PDF em anexo | Avaliador atualmente elegível e sem conflito, com designação vigente para o projeto |

No POST, envie `repositorio_url` na query e o arquivo como corpo binário com
`Content-Type: application/pdf`. A equipe vem do caminho. O servidor localiza o marco final
e a proposta aprovada na própria edição.

```sh
curl --request POST \
  --url "$API/equipes/$EQUIPE_ID/mentoria/submissao-final?repositorio_url=https%3A%2F%2Fgithub.com%2Fequipe%2Fsolucao" \
  --header "Authorization: Bearer $TOKEN" \
  --header "Content-Type: application/pdf" \
  --data-binary @relatorio.pdf
```

POST e GET retornam `id`, `submissao_id`, `marco_id`, `equipe_id`, `hackathon_id`,
`enviado_por`, `enviado_em`, `data_limite_no_envio`, `repositorio` (`url`, `validado_em`)
e `relatorio` (`url`, `tipo`, `tamanho_bytes`). As datas são UTC. O caminho retornado
em `relatorio.url` pertence à API e requer o token do usuário autorizado também no download.

| HTTP | Motivo |
| --- | --- |
| 401 | JWT ausente, inválido ou conta desativada |
| 403 | Conta pendente ou usuário sem permissão |
| 404 | Equipe, edição acessível, marco final ou submissão/relatório não encontrado |
| 409 | Equipe sem homologação ou sem aprovação, treinamento incompleto, edição indisponível, prazo inválido ou encerrado, ou tentativa de reenvio |
| 413 | Relatório com mais de 10.485.760 bytes |
| 415 | Tipo de mídia diferente de `application/pdf` no envio |
| 422 | URL inválida, repositório indisponível para acesso público ou PDF ilegível |
| 503 | Validação do GitHub temporariamente indisponível, inclusive por timeout ou limite da API |

## Regras do envio e histórico

A equipe precisa estar homologada e ter proposta aprovada no resultado homologado da própria
edição. A mentoria exige treinamento concluído e o envio deve ocorrer entre o início da mentoria
e o prazo inclusivo do marco `FINAL`. Edições `RASCUNHO`, `FINALIZADO` ou `CANCELADO` rejeitam
envios. As consultas históricas continuam disponíveis aos usuários autorizados. Prorrogações
preservam o prazo registrado no envio.

A entrega e os artefatos são gravados na mesma transação. O envio usa a trava compartilhada da
edição e a trava da equipe, como nas entregas parciais. As restrições de unicidade impedem envios
duplicados, inclusive concorrentes. A migration
[`V202611251300`](../migrations/V202611251300__submissao_final_mentoria.sql) acrescenta os
artefatos estruturados e vincula proposta, entrega, marco, equipe e edição por chaves compostas.
As rotas de entregas parciais conservam seus contratos e a política de imutabilidade. O painel
do mentor identifica a entrega final pelo mesmo calendário das demais entregas.

## Validação dos artefatos

- O relatório usa o PostgreSQL existente. A API mede os bytes efetivamente recebidos, limita
  o corpo a 10 MiB (10.485.760 bytes) e usa o parser pypdf em modo estrito para validar a estrutura
  do PDF. O arquivo precisa ter ao menos uma página e abrir sem senha. O banco calcula e limita
  o tamanho. O download sempre envia o arquivo como anexo autenticado.
- O RF45 usa a [API de metadados de repositórios do GitHub](https://docs.github.com/en/rest/repos/repos#get-a-repository).
  O backend valida o formato `https://github.com/dono/repositorio` e confirma que o repositório
  está acessível publicamente antes de aceitar o envio. A consulta usa destino HTTPS fixo
  `api.github.com`, caminho composto apenas por segmentos validados, limite de resposta e tempo
  total de cinco segundos. Redirecionamentos e proxies do ambiente ficam desativados.
- A Q13 segue aberta para repositórios privados. A validação implementada cobre o acesso
  público no instante do envio. A equipe responde por manter o acesso até o fim da avaliação
  (RN19). Monitoramento, revalidação posterior e concessão de acesso privado ficam pendentes.

## Avaliação técnica e versões

Designações antecipadas permanecem disponíveis após a homologação científica. Os artefatos só
são liberados para avaliação depois de um envio válido e para quem mantém uma designação
elegível e sem conflito. Consulte [Avaliação técnica](avaliacao-tecnica.md).

A BE-S6-08 deverá permitir substituições dentro do prazo com histórico (RF46). A entrega tem
identidade estável para receber versões imutáveis de artefatos, com autoria, horário e prazo de
cada versão. Até essa implementação, um novo POST para a equipe retorna 409 e o envio original
continua disponível.
