[← Voltar ao README](../README.md)

# Envio definitivo da proposta — BE-S4-08 e BE-S5-09

RF26 e RF28. As rotas exigem autenticação e conta ativa:

| Rota | Quem acessa | Resultado |
|------|-------------|-----------|
| `POST /equipes/{equipe_id}/proposta/enviar` | Líder técnico ou DEV | Envia o rascunho salvo e emite protocolo na mesma transação; sem corpo |
| `GET /equipes/{equipe_id}/proposta` | Integrantes ou DEV | Consulta somente a proposta enviada, com seu protocolo; sem envio retorna 404 |

O envio exige equipe `HOMOLOGADA`, tema existente e ativo da mesma edição, `tema_id`,
`titulo`, `descricao`, pelo menos um ODS entre 1 e 17 e `bases_dados`. Strings vazias ou
compostas apenas por espaços são rejeitadas com 422. `documento_url` permanece opcional.
DEV tem dispensa de vínculo e liderança, mas cumpre todas as regras de negócio.

Os dois limites `hackathon.propostas_inicio` e `propostas_fim` precisam estar configurados.
O momento do envio deve estar no intervalo inclusivo, comparado em UTC, independentemente
do período de inscrições. Datas sem fuso são interpretadas como UTC. Prazo ausente, futuro
ou encerrado, equipe não homologada, tema indisponível, resultado já homologado e uma segunda
chamada a `/enviar` retornam 409.

Ambas as rotas retornam os campos da proposta, `status = ENVIADA`, `enviado_em` e o objeto
`protocolo` com `id`, `numero`, `tipo`, `equipe_id`, `submissao_id`, `emitido_por` e
`emitido_em`, além de `versao` (1 no primeiro envio). As datas persistidas são UTC. A proposta
enviada não pode ser alterada nem consultada pelas rotas de rascunho, que foram preservadas;
para trocar o conteúdo, a equipe envia uma nova versão (veja
[Reenvio e versões](#reenvio-e-versões--be-s5-09)).

O bloqueio segue a ordem equipe → proposta. Envios concorrentes resultam em um sucesso
e um conflito, com um único protocolo; falha na emissão reverte também o status e a data
da proposta. A migration `V202610310900__protocolo_unico_proposta.sql` adiciona unicidade
por proposta aos protocolos do tipo `PROPOSTA`, complementando a unicidade do número.

No painel, `protocolo` continua representando a inscrição e `protocolo_proposta` traz
separadamente o número e a data da proposta, ou `null` antes do envio.

**E-mail do protocolo (RF28).** Ao enviar a proposta, o líder recebe o aviso `PROTOCOLO_PROPOSTA` com o número e o horário de Brasília, pela fila de e-mails, na mesma transação do envio (veja [E-mails](emails.md)). Se o envio da proposta falhar, nenhum e-mail é gerado.

## Reenvio e versões — BE-S5-09

RF27 e RN08. Uma proposta já enviada pode receber **nova versão** enquanto o processo dela
ainda não começou:

| Rota | Quem acessa | Resultado |
|------|-------------|-----------|
| `POST /equipes/{equipe_id}/proposta/reenviar` | Líder técnico ou DEV | Grava a nova versão com o conteúdo completo do corpo e emite novo protocolo |
| `GET /equipes/{equipe_id}/proposta/versoes` | Integrantes ou DEV | Histórico de envios, da versão mais recente para a original, cada um com o seu protocolo |

O corpo do reenvio traz a proposta inteira (`tema_id`, `titulo`, `descricao`, `ods`,
`bases_dados` e, opcional, `documento_url`) e passa pelas mesmas regras do envio. Campos a
mais, vazios ou só com espaços respondem 422.

**Política de reenvio.** A nova versão só é aceita se, no momento do pedido:

- a proposta já foi enviada (rascunho usa `/enviar`): senão, 409;
- o prazo de propostas está aberto (`propostas_inicio` ≤ agora ≤ `propostas_fim`, UTC): senão, 409;
- a equipe está `HOMOLOGADA` e não está em somente leitura: senão, 409;
- a proposta **não foi distribuída** (nenhuma designação de avaliador): senão, 409;
- a proposta **não tem avaliação**, nem rascunho nem dado legado: senão, 409;
- o resultado do hackathon **não foi homologado**: senão, 409;
- o tema está ativo e é da edição da equipe: senão, 404 ou 409.

**Histórico e protocolo por versão.** Cada envio (o primeiro e cada reenvio) vira uma linha
imutável em `versoes_proposta` (`numero` 1, 2, 3…) com o conteúdo enviado, quem enviou, quando,
e um protocolo `PROPOSTA` próprio, avisado por e-mail ao líder. A linha de `submissoes` guarda
sempre a versão mais recente, que é a distribuída, avaliada e homologada.
`GET /proposta` e o `protocolo_proposta` do painel mostram a versão mais recente (`versao`).

**Concorrência.** O envio e o reenvio travam primeiro a edição em modo compartilhado
(`FOR SHARE`), depois a equipe e a proposta. Reenvios simultâneos da mesma equipe são
serializados e recebem números diferentes. Distribuição e homologação travam a edição com
`FOR UPDATE`, então nenhum reenvio passa no meio delas: ou entra antes, ou recebe 409.

**Migração.** A migration `V202611131100__versoes_proposta.sql` cria `versoes_proposta`,
transforma cada proposta já enviada com protocolo na versão 1 (com esse mesmo protocolo) e
troca a unicidade `uq_protocolos_proposta_submissao` (um protocolo por proposta) por
`uq_versoes_proposta_protocolo` (um protocolo por versão). Proposta enviada sem protocolo
(dado legado) fica sem histórico: a consulta responde `versao = null` e `/versoes` vem vazio.
Um gatilho impede `UPDATE` em versões (`versao_proposta_imutavel`).

**Pendências:**

- A obrigatoriedade de anexo depende de regra de negócio explícita; esta entrega não exige
  anexo.
- O card cita a decisão do Squad 1 sobre o protocolo por versão; esta entrega adota "cada
  versão tem protocolo próprio e o anterior continua válido no histórico". Confirmar com o
  Squad 1.
- RF59 é citado no card, mas o texto do requisito não estava no repositório; nada específico
  dele foi implementado além do que está acima.

---

[← Voltar ao README](../README.md)
