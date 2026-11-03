[← Voltar ao README](../README.md)

# Equipes e membros — BE-S4-03

Todas as rotas exigem token e conta ativa; conta pendente recebe 403.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `POST /equipes` | PARTICIPANTE ou DEV | Recebe `hackathon_id` e `nome` opcional; cria equipe em `EM_FORMACAO` e vínculo `LIDER` do próprio usuário na mesma transação; demais perfis recebem 403 |
| `GET /equipes/minhas` | Usuário autenticado | Lista somente equipes das quais participa, em todas as edições; sem vínculo retorna `[]`, inclusive para DEV |
| `GET /equipes/{equipe_id}` | Integrante ou DEV | Consulta os dados da equipe |
| `PATCH /equipes/{equipe_id}` | Líder ou DEV | Altera somente `nome`, enquanto a equipe está em `EM_FORMACAO` e as inscrições estão abertas |
| `GET /equipes/{equipe_id}/membros` | Integrante ou DEV | Lista vínculos, funções e datas de entrada dos membros da equipe |
| `PATCH /equipes/{equipe_id}/membros/{usuario_id}` | Líder ou DEV | Altera somente `funcao`, durante `INSCRICOES` e em `EM_FORMACAO` |
| `DELETE /equipes/{equipe_id}/membros/{usuario_id}` | Líder ou DEV | Remove o vínculo do integrante, durante `INSCRICOES` e em `EM_FORMACAO`; retorna 204 sem corpo |

A criação e a edição seguem o critério de inscrições já usado pelos convites: `hackathon.status = INSCRICOES`. Os campos de datas de inscrições não são avaliados por esses fluxos. Fora das inscrições, a resposta é 409. Edição em outra situação também retorna 409. Equipe ou hackathon inexistente retorna 404; falta de vínculo ou liderança retorna 403.

O cliente não pode escolher outro líder nem enviar situação ou datas; campos extras são rejeitados com 422. No PATCH, `hackathon_id` também é rejeitado. `nome` continua opcional, aceita `null` e tem limite de 255 caracteres; PATCH vazio preserva os dados.

RN02 é garantida na consulta prévia e pela restrição única do banco, inclusive em disputa com aceites de convites. Falhas na criação revertem tanto a equipe quanto o vínculo do líder. Uma pessoa pode participar de edições diferentes.

A equipe pode ser criada com somente o líder, sem exigir o mínimo de integrantes, conclusão da inscrição, homologação ou aceite de termos nesta operação. O aceite continua nos endpoints próprios. Os limites permanecem configurados em `hackathon.min_integrantes` e `hackathon.max_integrantes`, sem novos valores fixos; o fluxo de convites continua usando o máximo configurado. A Q04 ainda precisa de validação.

## Gerenciamento dos membros — segunda etapa

A listagem retorna somente `equipe_id`, `usuario_id`, `hackathon_id`, `funcao` e `entrou_em`, sem dados privados das contas. A consulta continua permitida após o encerramento das inscrições; não integrantes recebem 403, salvo DEV. Toda alteração de membro verifica a liderança na própria equipe e busca o alvo pela chave composta `(equipe_id, usuario_id)`: um vínculo de outra equipe retorna 404.

O PATCH aceita `funcao` como `DESENVOLVEDOR`, `DESIGNER`, `NEGOCIOS`, `OUTRO` ou `null` (sem função). Campos extras são rejeitados com 422. Corpo vazio ou a mesma função preservam os dados. Remover ou rebaixar o líder, ou promover outro membro a `LIDER`, retorna 409, inclusive para DEV. Reenviar `LIDER` ao líder atual é apenas uma operação idempotente. Transferência de liderança aguarda definição de regra.

PATCH e DELETE usam o mesmo bloqueio da linha da equipe que o fluxo de convites, para coordenar alterações simultâneas de composição. Não há inclusão direta de integrantes: a entrada continua pelo aceite do convite (BE-S4-04). Alterar função não muda o total de membros; remover diminui o total e libera vaga, inclusive se o máximo configurado tiver sido reduzido. Nenhum mínimo é exigido durante a formação; a equipe pode ficar somente com o líder. O fluxo de convites continua aplicando `hackathon.max_integrantes`, sem novos limites fixos.

**Histórico e reconvite.** O DELETE remove apenas a linha de `membros_equipe`; convites `ACEITO` e aceites de termos permanecem intactos, com os mesmos estados, datas e versões. O índice parcial `uq_convites_equipe_email_ativo`, definido sobre `(equipe_id, lower(email))` para estados `PENDENTE` e `ACEITO`, continua impedindo um novo convite ao mesmo e-mail na mesma equipe (409), mesmo após a remoção. O convite antigo também não pode ser aceito novamente. Não se deve convertê-lo para `CANCELADO` ou `RECUSADO`, pois isso alteraria o histórico de um aceite real. Permitir retorno à mesma equipe exige uma decisão sobre a regra de reconvite e uma evolução específica do modelo/índice; ficou pendente nesta etapa. A remoção libera a unicidade de participação por hackathon: o usuário pode aceitar um convite de outra equipe da mesma edição, sujeito às regras já existentes.

**Aviso ao removido (RF24).** Não há serviço, fila ou integração de notificações/e-mail implementados no projeto. O aviso permanece pendente de infraestrutura; o endpoint não envia nem simula notificação. A resposta 204 confirma apenas a remoção do vínculo. A Q04 sobre tamanho de equipes também continua pendente.

Exclusão de equipes, transferência de liderança, conclusão da inscrição, homologação e notificações por e-mail não fazem parte desta entrega. Migrations e o fluxo de convites e termos foram preservados nesta etapa.

---

[← Voltar ao README](../README.md)
