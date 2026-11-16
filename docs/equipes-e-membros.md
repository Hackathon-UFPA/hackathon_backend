[← Voltar ao README](../README.md)

# Equipes e membros — BE-S4-03

Todas as rotas exigem token e conta ativa; conta pendente recebe 403.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `POST /equipes` | PARTICIPANTE ou DEV | Recebe `hackathon_id` e `nome` opcional; cria equipe em `EM_FORMACAO` e vínculo `LIDER` do próprio usuário na mesma transação; demais perfis recebem 403. Aceita também `categoria`, `tipo_lider` e `integrantes` (BE-S5-01, veja abaixo) |
| `GET /equipes/{equipe_id}/composicao` | Integrante ou DEV | Para cada pessoa, o que o líder indicou, o que ela já confirmou e as pendências individuais (BE-S5-01) |
| `PUT /equipes/{equipe_id}/composicao` | Líder ou DEV | Substitui a categoria e a composição inteira, durante as inscrições e em `EM_FORMACAO` (RF24, BE-S5-01) |
| `GET /equipes/minhas` | Usuário autenticado | Lista somente equipes das quais participa, em todas as edições; sem vínculo retorna `[]`, inclusive para DEV |
| `GET /equipes/{equipe_id}` | Integrante ou DEV | Consulta os dados da equipe |
| `PATCH /equipes/{equipe_id}` | Líder ou DEV | Altera somente `nome`, enquanto a equipe está em `EM_FORMACAO` e as inscrições estão abertas |
| `GET /equipes/{equipe_id}/membros` | Integrante ou DEV | Lista vínculos, funções e datas de entrada dos membros da equipe |
| `PATCH /equipes/{equipe_id}/membros/{usuario_id}` | Líder ou DEV | Altera somente `funcao`, durante `INSCRICOES` e em `EM_FORMACAO` |
| `DELETE /equipes/{equipe_id}/membros/{usuario_id}` | Líder ou DEV | Remove o vínculo do integrante, durante `INSCRICOES` e em `EM_FORMACAO`; retorna 204 sem corpo |

A criação e a edição seguem o critério de inscrições já usado pelos convites: `hackathon.status = INSCRICOES`. Os campos de datas de inscrições não são avaliados por esses fluxos. Fora das inscrições, a resposta é 409. Edição em outra situação também retorna 409. Equipe ou hackathon inexistente retorna 404; falta de vínculo ou liderança retorna 403.

O cliente não pode escolher outro líder nem enviar situação ou datas; campos extras são rejeitados com 422 (as exceções são `categoria`, `tipo_lider` e `integrantes`, da BE-S5-01). No PATCH, `hackathon_id` também é rejeitado. `nome` continua opcional, aceita `null` e tem limite de 255 caracteres; PATCH vazio preserva os dados.

RN02 é garantida na consulta prévia e pela restrição única do banco, inclusive em disputa com aceites de convites. Falhas na criação revertem tanto a equipe quanto o vínculo do líder. Uma pessoa pode participar de edições diferentes.

A equipe pode ser criada com somente o líder, sem exigir o mínimo de integrantes, conclusão da inscrição, homologação ou aceite de termos nesta operação. O aceite continua nos endpoints próprios. Os limites permanecem configurados em `hackathon.min_integrantes` e `hackathon.max_integrantes`, sem novos valores fixos; o fluxo de convites continua usando o máximo configurado. A Q04 ainda precisa de validação.

## Categorias e composição informada pelo líder (BE-S5-01)

Decisão da reunião de 05/11/2026 (RF01, RF18, RF21 a RF24; RN01, RN02, RN03, RN05, RN25): o líder informa a **categoria** da equipe, `ESTUDANTES`, `PROFISSIONAIS` ou `MISTA`, e **toda a composição em uma operação**. Essa decisão tem precedência operacional provisória sobre o documento da Sprint 2, e a elegibilidade ainda precisa ser validada formalmente com o Squad 1 (veja a política abaixo).

### O que o líder indica e o que cada pessoa confirma

| Indicado pelo líder (não verificado) | Confirmado por cada pessoa, com a própria conta |
|--------------------------------------|--------------------------------------------------|
| `categoria` da equipe; de cada integrante, `nome`, `email` e `tipo_integrante` (`ESTUDANTE` ou `PROFISSIONAL`), e o `tipo_lider` | Dados pessoais, aceite do regulamento e do termo de consentimento (RN05), comprovante de vínculo (RF01, RN25) e aceite do convite |

Nada do lado direito passa pelo líder: `integrantes[]` só aceita `nome`, `email` e `tipo_integrante` (qualquer outro campo, como `termos_ids` ou um link de comprovante, dá 422). O aceite do convite e dos termos usa sempre o usuário logado, e o convite só responde ao destinatário (para os demais, 404). A pessoa também **não escolhe o próprio tipo**: o aceite copia o `tipo_integrante` do convite para o vínculo.

### Criar com a composição inteira

`POST /equipes` aceita, além de `hackathon_id` e `nome`:

| Campo | Regra |
|-------|-------|
| `categoria` | Opcional. Omitida, vale `ESTUDANTES` (comportamento de antes da decisão) |
| `tipo_lider` | Opcional, exceto na `MISTA` |
| `integrantes` | Opcional. A composição completa, **sem o líder** (nome, e-mail e `tipo_integrante`). Omitida, só o líder é criado, como antes |

Com `integrantes`, tudo é conferido **antes de gravar** e grava na mesma transação (equipe, vínculo do líder e convites, com o aviso por e-mail e na central). Qualquer falha dá 422 e nada é gravado:

- **Limites (RN01, Q04):** o total, líder incluído, fica entre `hackathon.min_integrantes` e `max_integrantes` (3 a 5 por padrão; a Q04 segue em validação). Sem `integrantes`, o mínimo só vale na conclusão da inscrição, como antes.
- **Categoria aceita pela edição:** veja a política.
- **Tipos coerentes com a categoria:** `ESTUDANTES` só com `ESTUDANTE`; `PROFISSIONAIS` só com `PROFISSIONAL`; `MISTA` com ao menos um de cada. Nas duas primeiras o tipo pode ser omitido (vale o da categoria); na `MISTA` ele é obrigatório para todos.
- **E-mails:** sem repetição (sem diferenciar maiúsculas) e sem o do próprio líder. No máximo 20 itens por pedido.

A resposta continua sendo a `EquipeResponse` (agora com `categoria`). As pendências individuais ficam em `GET /equipes/{id}/composicao`.

### Consultar a composição

`GET /equipes/{id}/composicao` (integrantes e DEV) devolve a categoria, os limites, `total_integrantes` (quem já entrou), `total_indicados` (com os convites em aberto), as `pendencias_da_equipe` (tamanho, categoria, termos não publicados) e, para cada pessoa:

```json
{
  "indicado_pelo_lider": {"nome": "Maria", "email": "maria@example.com", "tipo_integrante": "PROFISSIONAL", "funcao": null},
  "confirmado_pelo_integrante": {"integrante": true, "usuario_id": "...", "convite": "ACEITO", "conta_ativa": true, "termos_aceitos": false, "comprovante": null},
  "pendencias": [{"codigo": "TERMOS_NAO_ACEITOS", "mensagem": "...", "usuario_id": "...", "bloqueia_conclusao": true}]
}
```

Convite em aberto aparece com `integrante = false` e `usuario_id` vazio: a resposta **não revela se o e-mail tem conta** nem se a pessoa já está em outra equipe. As pendências individuais usam os códigos do painel (`CONVITE_NAO_ACEITO`, `TERMOS_NAO_ACEITOS`, `COMPROVANTE_NAO_ENVIADO`, `COMPROVANTE_PENDENTE`, `COMPROVANTE_RECUSADO`, `CONTA_DESATIVADA`) e, só aqui, `CONVITE_PENDENTE` e `CONVITE_RECUSADO`. Para o profissional, as mensagens do comprovante falam em "vínculo profissional".

### Substituir a composição (RF24)

`PUT /equipes/{id}/composicao` recebe `categoria`, `tipo_lider` (opcional, mantém o atual) e `integrantes` (a lista completa), com as mesmas regras do POST. Só o líder (RN03; DEV como exceção), com a equipe em `EM_FORMACAO` e inscrições abertas (RN06). Na mesma transação:

- quem já entrou e não está na lista é **retirado e avisado** na central de notificações (tipo `INSCRICAO`, `dados.evento = REMOVIDO`; o aviso por e-mail ainda não existe);
- convites em aberto de quem saiu ficam `CANCELADO`;
- quem é novo recebe convite (e-mail e central), em nome do líder da equipe;
- quem continua tem o `tipo_integrante` atualizado, se mudou.

A pessoa é identificada pelo e-mail que o líder digitou no convite. Quem aceitou, foi retirado e é incluído de novo recebe **409**: o convite `ACEITO` continua no histórico e ainda impede o reconvite à mesma equipe (decisão pendente, a mesma da seção de remoção de membros). `DELETE /equipes/{id}/membros/{usuario_id}` também avisa o removido a partir desta entrega.

Concorrência: a rota trava os convites pendentes e depois a equipe, na mesma ordem do aceite de convite (que trava o convite e depois a equipe), então os dois nunca ficam esperando um pelo outro. O convite retirado vira 409 para quem tentar aceitá-lo em seguida.

### Política de elegibilidade provisória

O documento da Sprint 2 previa só graduandos com vínculo acadêmico; a decisão de 05/11 inclui profissionais e mistos. Enquanto o Squad 1 não valida a regra, ela é **configuração da edição**, sem código a mudar:

- `hackathon.aceita_equipe_estudantes`, `aceita_equipe_profissionais` e `aceita_equipe_mista` (padrão: todas verdadeiras; ao menos uma precisa ficar verdadeira). O Organizador ajusta por `PATCH /admin/hackathons/{id}`. Categoria que a edição não aceita dá 422 com a lista das aceitas; para equipe já criada, vira a pendência `CATEGORIA_NAO_PERMITIDA`, que só bloqueia a **conclusão** (quem já concluiu não volta atrás por mudança de política).
- O vínculo comprovado depende do tipo indicado: o estudante comprova vínculo acadêmico, o profissional, vínculo profissional. Hoje os dois usam o mesmo fluxo de comprovante e a mesma conferência (RF21, Q25); a diferença está na mensagem das pendências. Se o Squad 1 definir outro documento ou outro conferente para profissionais, o ponto de ajuste é `app/services/homologacao.py`.
- `CATEGORIA_INCOERENTE` (bloqueia a conclusão) aparece quando os tipos dos integrantes deixam de formar a categoria, por exemplo se alguém é removido de uma equipe `MISTA`.

**Pontos a validar formalmente:** (1) se profissionais e mistos podem concorrer em todas as edições; (2) qual comprovante vale para o profissional e quem o confere; (3) se a `MISTA` exige mesmo ao menos um de cada tipo; (4) a Q04 (3 a 5).

### Compatibilidade com dados legados

A migration preenche `ESTUDANTES` e `ESTUDANTE` nas equipes, convites e vínculos existentes e libera as três categorias em todas as edições. Clientes que não enviam os campos novos seguem funcionando: `POST /equipes` sem `categoria` cria `ESTUDANTES`, o convite avulso sem `tipo_integrante` herda o tipo da categoria (na `MISTA` o tipo é obrigatório, 422), e as respostas só ganharam campos (`categoria`, `tipo_integrante`).

### Unicidade por edição

RN02 segue garantida pela consulta prévia e pela restrição `uq_membros_equipe_hackathon_usuario`: o líder que já está em equipe da edição recebe 409 (também em criações simultâneas). Quem é convidado e já está em outra equipe da mesma edição só descobre ao aceitar (409). Na criação isso **não** é checado de propósito: avisar o líder revelaria quem participa de outra equipe.

## Gerenciamento dos membros — segunda etapa

A listagem retorna somente `equipe_id`, `usuario_id`, `hackathon_id`, `funcao` e `entrou_em`, sem dados privados das contas. A consulta continua permitida após o encerramento das inscrições; não integrantes recebem 403, salvo DEV. Toda alteração de membro verifica a liderança na própria equipe e busca o alvo pela chave composta `(equipe_id, usuario_id)`: um vínculo de outra equipe retorna 404.

O PATCH aceita `funcao` como `DESENVOLVEDOR`, `DESIGNER`, `NEGOCIOS`, `OUTRO` ou `null` (sem função). Campos extras são rejeitados com 422. Corpo vazio ou a mesma função preservam os dados. Remover ou rebaixar o líder, ou promover outro membro a `LIDER`, retorna 409, inclusive para DEV. Reenviar `LIDER` ao líder atual é apenas uma operação idempotente. Transferência de liderança aguarda definição de regra.

PATCH e DELETE usam o mesmo bloqueio da linha da equipe que o fluxo de convites, para coordenar alterações simultâneas de composição. Não há inclusão direta de integrantes: a entrada continua pelo aceite do convite (BE-S4-04). Alterar função não muda o total de membros; remover diminui o total e libera vaga, inclusive se o máximo configurado tiver sido reduzido. Nenhum mínimo é exigido durante a formação; a equipe pode ficar somente com o líder. O fluxo de convites continua aplicando `hackathon.max_integrantes`, sem novos limites fixos.

**Histórico e reconvite.** O DELETE remove apenas a linha de `membros_equipe`; convites `ACEITO` e aceites de termos permanecem intactos, com os mesmos estados, datas e versões. O índice parcial `uq_convites_equipe_email_ativo`, definido sobre `(equipe_id, lower(email))` para estados `PENDENTE` e `ACEITO`, continua impedindo um novo convite ao mesmo e-mail na mesma equipe (409), mesmo após a remoção. O convite antigo também não pode ser aceito novamente. Não se deve convertê-lo para `CANCELADO` ou `RECUSADO`, pois isso alteraria o histórico de um aceite real. Permitir retorno à mesma equipe exige uma decisão sobre a regra de reconvite e uma evolução específica do modelo/índice; ficou pendente nesta etapa. A remoção libera a unicidade de participação por hackathon: o usuário pode aceitar um convite de outra equipe da mesma edição, sujeito às regras já existentes.

**Aviso ao removido (RF24).** A infraestrutura de e-mail existe (veja [E-mails](emails.md)), mas ainda não há um tipo de e-mail nem gatilho para a remoção de integrante: o endpoint não envia nem simula notificação. A resposta 204 confirma apenas a remoção do vínculo. A Q04 sobre tamanho de equipes também continua pendente.

Exclusão de equipes, transferência de liderança, conclusão da inscrição, homologação e notificações por e-mail não fazem parte desta entrega. Migrations e o fluxo de convites e termos foram preservados nesta etapa.

---

[← Voltar ao README](../README.md)
