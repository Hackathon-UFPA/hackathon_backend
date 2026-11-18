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

Se o link vencer, o líder cancela o convite e convida de novo (convite cancelado libera o e-mail), ou substitui a composição (`PUT /equipes/{id}/composicao`); o novo convite sai com um link novo.

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

## Compatibilidade

- Migration `V202611161500__cadastro_por_convite_idempotencia.sql`: `convites.token_hash`, `token_expira_em` e `token_utilizado_em`; `equipes.criada_por`, `chave_idempotencia` e `hash_requisicao`. Convites e equipes anteriores seguem válidos (campos nulos).
- Sem `Idempotency-Key`, o `POST /equipes` se comporta como antes. As respostas não ganharam campos; o token nunca aparece em resposta da API.
- `app/services/equipe.py`: `criar` passa a devolver `(equipe, criada)`.
- Nova variável de ambiente `CONVITE_CADASTRO_MINUTOS` (padrão 10080).

## Pontos em aberto

- **Comprovante opcional no cadastro por convite:** diverge do RF01, que o exige no cadastro. Foi escolhido para o convidado preencher o vínculo depois, junto com a autodeclaração (BE-S5-03). Se o grupo preferir exigi-lo já aqui, basta tornar `comprovante_url` obrigatório em `CadastroPorConviteRequest`.
- **Tipo do comprovante no cadastro:** no cadastro por convite, o comprovante opcional nasce com o tipo de vínculo que o líder indicou no convite (`ESTUDANTE` ou `PROFISSIONAL`), que é o que a homologação confere ([BE-S5-03](autodeclaracao-e-comprovantes.md)). O cadastro público continua registrando o comprovante como `ESTUDANTE`.
- **Edição do cadastro (BE-S6-14):** no link de convite, o hackathon vem sempre da equipe, mesmo com outras edições abertas. O corpo continua recusando `hackathon_id` (422). Quem optar pelo cadastro público informa o ID da edição no corpo; para declarar depois ou enviar comprovante, deve selecionar a mesma edição explicitamente. Veja [contratos por hackathon](cadastro-por-hackathon.md).
- **Reenvio de link vencido:** não há rota de reenvio; o líder cancela e convida de novo ou substitui a composição.
- **Notificação retroativa:** o convite vira aviso na central quando a conta passa a existir; a central em si continua exigindo conta ativa.

---

[← Voltar ao README](../README.md)
