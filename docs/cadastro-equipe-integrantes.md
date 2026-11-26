[← Voltar ao README](../README.md)

# Cadastro da equipe e dos integrantes em um fluxo — BE-S5-02

RF01, RF18, RF19, RF22, RF23; RN01 a RN06. Depende da [BE-S5-01](equipes-e-membros.md#categorias-e-composição-informada-pelo-líder-be-s5-01) (categoria e composição informada pelo líder) e da [BE-S5-05](emails.md) (fila de e-mails).

Decisões da reunião de 05/11/2026 têm precedência operacional provisória sobre o documento da Sprint 2.

## O que já vinha da BE-S5-01 e o que esta tarefa acrescenta

O líder já cadastra a equipe com a lista completa de integrantes em uma operação atômica (`POST /equipes` com `integrantes`), com convites individuais e a equipe nascendo `EM_FORMACAO`. Esta tarefa fecha o que faltava para quem **não tem conta**, para o retry do pedido e para a conta recém-criada:

| Tema | Como fica |
|------|-----------|
| Convidado com conta | O convite é associado à conta na criação (`convites.usuario_id`) e o e-mail leva a `/convites` |
| Convidado **sem conta** | O líder **não cria conta nem define senha**. O e-mail traz um link de uso único para a pessoa criar o próprio acesso (abaixo) |
| Retry do `POST /equipes` | Cabeçalho `Idempotency-Key`: repetir o pedido devolve a equipe já criada, sem duplicar convites nem e-mails |
| Conta criada depois do convite | Os convites em aberto do mesmo e-mail passam a valer para a conta nova e aparecem na central |
| Conta pendente | Pode ver e responder aos convites e aceitar os termos (RN25 continua valendo para a homologação) |

## Cadastro próprio pelo link do convite

Ao convidar um e-mail sem conta, o convite ganha um token aleatório de uso único e validade de `CONVITE_CADASTRO_MINUTOS` (padrão 7 dias). O banco guarda **só o SHA-256** (`convites.token_hash`), como nos convites de mentor e nos links de redefinição de senha; o valor puro existe apenas no e-mail, no fragmento do endereço (`FRONTEND_URL/cadastro#convite=<token>`), para não ir a logs de servidor.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `POST /auth/cadastro/convite/consulta` | Público, com o token no corpo | Mostra o convite (e-mail fixo, nome indicado, equipe, líder, tipo) para a página de cadastro. Não gasta o token |
| `POST /auth/cadastro/convite` | Público, com o token no corpo | A pessoa cria o acesso: `token`, `senha` e, opcionalmente, `nome`, `instituicao`, `curso`, `periodo` e `comprovante_url` |

**Regras.**

- O **e-mail e o papel não vêm do cliente**: o e-mail é o do convite e o papel é sempre `PARTICIPANTE`. Qualquer campo extra (`email`, `papel`, `situacao_conta`, `hackathon_id`...) dá 422. A senha é da própria pessoa e segue a regra do cadastro (8 a 128 caracteres, com letra e número).
- O token prova a posse do e-mail, então o endereço **já nasce confirmado** (`email_confirmado_em`). A conta nasce `PENDENTE` (RN25): o vínculo continua sendo comprovado e conferido à parte.
- O comprovante é **opcional aqui** (no cadastro público do RF01 ele é obrigatório): a pessoa pode enviá-lo depois em `POST /comprovantes`, e a equipe só homologa com o vínculo aprovado (RF23).
- **Cadastrar não aceita o convite nem os termos.** Isso a pessoa faz depois, com a própria conta (`POST /convites/{id}/aceitar`). Termos e convite continuam individuais (RN05).
- **Uso único e simultaneidade:** o convite é travado durante o cadastro; dois usos ao mesmo tempo do mesmo link resultam em um 201 e um 400. Se algo falhar, nada é gravado e o link continua valendo.
- **Token inválido: sempre o mesmo 400.** Inexistente, vencido, já usado, convite que não está mais `PENDENTE` (aceito, recusado ou cancelado), equipe que já fechou a composição ou inscrições encerradas dão a mesma resposta `Link de convite inválido, vencido ou já utilizado.`, para o link não revelar o que existe.
- Se já existe conta com o e-mail do convite: **409**. A pessoa entra com ela e responde ao convite.
- A resposta é o `UsuarioResponse` (sem senha nem hash). Para entrar, a pessoa usa `POST /auth/login`.

Se o link vencer, o líder [reenvia o convite](#reenvio-e-correção-de-convite-pendente--be-s5-06): o link novo sai sem cancelar nada. Cancelar e convidar de novo (convite cancelado libera o e-mail) e substituir a composição (`PUT /equipes/{id}/composicao`) continuam valendo.

### Conta pendente responde ao convite

Quem se cadastrou pelo link ainda aguarda a conferência do comprovante, mas precisa aceitar a participação e os termos com a própria conta. Por isso `GET /convites/meus`, `POST /convites/{id}/aceitar`, `POST /convites/{id}/recusar`, `GET /hackathons/{id}/termos/vigentes` e `POST /hackathons/{id}/termos/aceites` aceitam a conta pendente (dependência `usuario_convidado`). Mentor sem ativação (RN33) continua barrado. Criar equipe, convidar e a central de notificações (`/me/notificacoes`) continuam exigindo conta ativa.

## Idempotência do `POST /equipes`

Com o cabeçalho opcional `Idempotency-Key` (1 a 128 caracteres):

| Situação | Resposta |
|----------|----------|
| Primeiro pedido com a chave | `201`, equipe criada |
| Mesma chave, mesmo líder e mesmo conteúdo | `200` com a mesma equipe, **sem** novos convites nem e-mails |
| Mesma chave, mesmo líder, conteúdo diferente | `409` |
| Chave vazia ou com mais de 128 caracteres | `422` |
| Sem o cabeçalho | Como antes: um segundo pedido do mesmo líder na edição dá `409` |

A chave vale **por líder** (`equipes.criada_por`) e fica na equipe junto com o SHA-256 do conteúdo (`hash_requisicao`; e-mails entram em minúsculas). Pedidos simultâneos com a mesma chave geram uma equipe só: os que perdem a disputa devolvem a equipe do vencedor. Um pedido recusado por validação (422) não consome a chave.

## Sobreposição, duplicidade e prazos

- **Duplicidade:** e-mail repetido na lista (sem diferenciar maiúsculas) e o e-mail do líder na lista dão 422; reconvidar o mesmo e-mail em aberto na mesma equipe dá 409.
- **Sobreposição (RN02):** o líder que já está em equipe da edição recebe 409, e a unicidade `uq_membros_equipe_hackathon_usuario` vale também em criações simultâneas. Quem é convidado e já está em outra equipe só descobre ao **aceitar** (409): a criação não revela quem participa de outra equipe (decisão de privacidade, a mesma da BE-S5-01).
- **Prazos (RN06):** criação, convite, aceite e cadastro pelo link só valem com as inscrições abertas e a equipe em formação. O link também tem validade própria.
- **Transações:** equipe, vínculo do líder, convites e avisos gravam juntos; qualquer falha reverte tudo.
- **Equipe não homologada até as confirmações:** a equipe nasce `EM_FORMACAO`. Os convidados só entram ao aceitar, e a homologação segue exigindo termos aceitos por todos e vínculo aprovado (RF22, RF23).

## E-mail do convite

O tipo `CONVITE_EQUIPE` ganhou uma variante para quem não tem conta: o texto explica que a pessoa ainda não tem acesso, o botão vira "Criar meu acesso" e o endereço leva ao cadastro com o token. A variante é escolhida pelo valor opcional `novo_usuario` do contexto; para quem tem conta nada muda. Como no restante da fila ([E-mails](emails.md)), o corpo renderizado fica em `emails_outbox`, onde o token puro também aparece: o acesso à fila é restrito ao Organizador.

## Reenvio e correção de convite pendente — BE-S5-06

RF01, RF18, RF19, RF20, RF60. O líder renova o aviso de um convite que ainda não foi respondido, ou corrige o nome e o e-mail dele, sem cancelar e convidar de novo.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `POST /convites/{id}/reenviar` | Líder da equipe (DEV passa) | Reenvia ao mesmo e-mail, inclusive com o link vencido. `200` com o `ConviteResponse` |
| `PATCH /convites/{id}` | Líder da equipe (DEV passa) | Corrige `nome` e/ou `email` (ao menos um; campo extra dá 422). `200` com o `ConviteResponse` |

**Erros.** `401` sem token; `403` conta pendente ou integrante da equipe que não é o líder; `404` convite inexistente **ou** de uma equipe da qual quem pede não faz parte (a resposta é a mesma, para não revelar convites alheios); `409` convite já aceito, recusado ou cancelado, inscrições fechadas, equipe fora de `EM_FORMACAO` ou limite de renovações esgotado; `429` reenvio antes do intervalo mínimo, com o cabeçalho `Retry-After` (segundos). No `PATCH`, ainda `409` para e-mail já convidado na equipe, e-mail de quem já é integrante e equipe sem vagas, e `422` para corpo vazio ou e-mail inválido.

**Fluxo do token.** O convite é travado (`FOR UPDATE`) e, depois, a equipe, na mesma ordem do aceite. Dois pedidos simultâneos se enfileiram e sobra um único token válido.

- *E-mail sem conta:* gera um token novo, grava só o hash (`convites.token_hash`), renova `token_expira_em` e zera `token_utilizado_em`. O link anterior deixa de existir e passa a dar o mesmo `400` genérico dos links inválidos. O valor puro só vai no e-mail.
- *E-mail com conta:* o convite é ligado à conta (`usuario_id`), o link de cadastro anterior é invalidado e a pessoa responde logada, em `/convites`. A conta é buscada pelo e-mail **no momento do reenvio**: quem criou conta depois do convite também cai neste caminho.

**Avisos.** Cada envio tem a própria chave de idempotência, `convite:{id}` no primeiro e `convite:{id}:envio:{n}` nos seguintes (`n` = `convites.reenvios`), senão a fila e a central tratariam o aviso novo como repetido. Quem tem conta recebe a notificação na central **e** o e-mail; quem não tem recebe o e-mail com o link novo. O aviso anterior que ainda estava `PENDENTE` em `emails_outbox` é retirado (`FALHA` com `cancelado_em`, sem corpo, então o token antigo some da tabela). Se o worker já o pegou (`ENVIANDO`), enviou (`ENVIADO`) ou ele falhou, nada é feito e não há erro: o link daquele e-mail já está invalidado pelo hash novo.

**Anti-abuso.**

| Regra | Variável | Padrão | Resposta |
|-------|----------|--------|----------|
| Intervalo mínimo entre reenvios simples | `CONVITE_REENVIO_INTERVALO_SEGUNDOS` | 300 | `429` + `Retry-After` |
| Máximo de renovações por convite (reenvios **e** trocas de e-mail) | `CONVITE_REENVIO_MAX` | 5 | `409` |

O intervalo conta a partir do último aviso (a criação do convite também conta). A **troca de e-mail** pelo `PATCH` gasta uma renovação do máximo, mas **não** respeita o intervalo, para o líder corrigir um endereço errado na hora; depois dela, o reenvio simples espera o intervalo normalmente. O `PATCH` só de nome não envia nada, não gasta renovação e não mexe no token.

**Correção (`PATCH`).** Só vale com o convite `PENDENTE`. Trocar o e-mail revalida: e-mail já convidado na equipe (`409`, inclusive em pedidos simultâneos, pelo índice único), e-mail de quem já é integrante (`409`), máximo de integrantes contando os convites pendentes (`409`) e o período de inscrições (`409`). O e-mail antigo deixa de poder usar o link. Se o novo e-mail já tem conta, o convite é ligado a ela e a notificação vai à central; a notificação que a conta antiga já tinha recebido é marcada como lida, e o convite deixa de ser dela (responder dá `404`). **A tabela `usuarios` nunca é alterada:** trocar o e-mail de uma conta confirmada exige um processo de segurança próprio e não faz parte disto.

**Privacidade.** A resposta e os logs não trazem token nem e-mail de terceiros; as mensagens de `409` não citam e-mails.

**Contrato para o frontend.** As rotas são novas; nada do que existia mudou. O `ConviteResponse` (criação, listagem, cancelamento, reenvio e correção) ganhou dois campos, ambos aditivos:

| Campo | Tipo | Significado |
|-------|------|-------------|
| `reenvios` | inteiro | Quantas vezes o aviso foi renovado (reenvio ou troca de e-mail) |
| `proximo_reenvio_em` | data e hora com fuso, ou `null` | Quando o reenvio simples volta a valer. Considera **só o intervalo mínimo**; uma data no passado significa que já pode reenviar. É `null` quando o limite de renovações se esgotou **ou o convite já não está pendente** |

Trate o `429` lendo o `Retry-After`; os 409 de limite esgotado sugerem cancelar o convite e convidar de novo.

## Compatibilidade

- Migration `V202611161500__cadastro_por_convite_idempotencia.sql`: `convites.token_hash`, `token_expira_em` e `token_utilizado_em`; `equipes.criada_por`, `chave_idempotencia` e `hash_requisicao`. Convites e equipes anteriores seguem válidos (campos nulos).
- Sem `Idempotency-Key`, o `POST /equipes` se comporta como antes. As respostas não ganharam campos; o token nunca aparece em resposta da API.
- `app/services/equipe.py`: `criar` passa a devolver `(equipe, criada)`.
- Nova variável de ambiente `CONVITE_CADASTRO_MINUTOS` (padrão 10080).
- Migration `V202611261000__reenvio_convites.sql` (BE-S5-06): `convites.reenvios` (`smallint`, padrão 0) e `convites.ultimo_envio_em` (`timestamptz`, UTC, preenchido com `enviado_em` nos convites antigos). As variáveis `CONVITE_REENVIO_INTERVALO_SEGUNDOS` e `CONVITE_REENVIO_MAX` estão no `.env.example`.

## Pontos em aberto

- **Comprovante opcional no cadastro por convite:** diverge do RF01, que o exige no cadastro. Foi escolhido para o convidado preencher o vínculo depois, junto com a autodeclaração (BE-S5-03). Se o grupo preferir exigi-lo já aqui, basta tornar `comprovante_url` obrigatório em `CadastroPorConviteRequest`.
- **Tipo do comprovante no cadastro:** no cadastro por convite, o comprovante opcional nasce com o tipo de vínculo que o líder indicou no convite (`ESTUDANTE` ou `PROFISSIONAL`), que é o que a homologação confere ([BE-S5-03](autodeclaracao-e-comprovantes.md)). O cadastro público continua registrando o comprovante como `ESTUDANTE`.
- **Edição do cadastro (BE-S6-14):** no link de convite, o hackathon vem sempre da equipe, mesmo com outras edições abertas. O corpo continua recusando `hackathon_id` (422). Quem optar pelo cadastro público informa o ID da edição no corpo; para declarar depois ou enviar comprovante, deve selecionar a mesma edição explicitamente. Veja [contratos por hackathon](cadastro-por-hackathon.md).
- **Reenvio e correção:** veja a [seção própria](#reenvio-e-correção-de-convite-pendente--be-s5-06). Fica em aberto com o grupo se a Squad 1 validou a regra de corrigir só enquanto o convite está pendente (foi o que o escopo de 19/11 descreveu).
- **Notificação retroativa:** o convite vira aviso na central quando a conta passa a existir; a central em si continua exigindo conta ativa.

---

[← Voltar ao README](../README.md)
