[← Voltar ao README](../README.md)

# Envio definitivo da proposta — BE-S4-08

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
ou encerrado, equipe não homologada, tema indisponível e reenvio retornam 409.

Ambas as rotas retornam os campos da proposta, `status = ENVIADA`, `enviado_em` e o objeto
`protocolo` com `id`, `numero`, `tipo`, `equipe_id`, `submissao_id`, `emitido_por` e
`emitido_em`. As datas persistidas são UTC. A proposta enviada é imutável: não pode ser
alterada nem consultada pelas rotas específicas de rascunho, que foram preservadas.

O bloqueio segue a ordem equipe → proposta. Envios concorrentes resultam em um sucesso
e um conflito, com um único protocolo; falha na emissão reverte também o status e a data
da proposta. A migration `V202610310900__protocolo_unico_proposta.sql` adiciona unicidade
por proposta aos protocolos do tipo `PROPOSTA`, complementando a unicidade do número.

No painel, `protocolo` continua representando a inscrição e `protocolo_proposta` traz
separadamente o número e a data da proposta, ou `null` antes do envio.

**Pendências:** envio do protocolo por e-mail depende de integração futura e não é
executado nem simulado. A obrigatoriedade de anexo depende de regra de negócio explícita;
esta entrega não exige anexo.

---

[← Voltar ao README](../README.md)
