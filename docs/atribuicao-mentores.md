[← Voltar ao README](../README.md)

# Atribuição de mentores — BE-S5-11

RF38, RN16, RN24 e RN33, conforme os critérios do card. A branch `feat/be-s5-11-atribuicao-mentores` parte do merge `4a4c168` (PR #16), que integra a BE-S5-10 e a revisão `5a5172c`. A implementação reutiliza `app.services.mentor.validar_elegibilidade`, os aceites por edição e a fila de e-mails do PR #15.

## Regras e autorização

- Comitê Científico atribui, substitui e encerra mentoria. Organizador pode executar as mesmas operações como exceção administrativa; DEV mantém o acesso previsto no projeto. Nenhum desses perfis dispensa as regras de negócio.
- A equipe precisa de proposta **aprovada em resultado homologado na própria edição**. Equipe apenas homologada na inscrição não basta. Proposta reprovada ou sem resultado não permite atribuição.
- O treinamento da edição precisa ter sido concluído, e a edição não pode estar `FINALIZADO` ou `CANCELADO`.
- `validar_elegibilidade()` exige papel MENTOR, conta ativa, perfil RN33 concluído, senha, capacidade positiva e aceites dos termos vigentes **da edição da equipe**. Não exige comprovante acadêmico.
- Cada equipe tem no máximo um vínculo vigente (`encerrada_em IS NULL`). A capacidade é a soma de todos os vínculos vigentes do mentor, em **todas as edições**, mesmo quando o mentor está temporariamente desativado.
- Desativar o mentor pela BE-S5-10 bloqueia novas atribuições, preservando os vínculos existentes. O gestor deve substituí-los ou encerrá-los explicitamente. A equipe vê o contato atual com `mentor.ativo=false`; não recebe dados de outro mentor automaticamente.
- Reduzir `max_equipes` abaixo do número de vínculos vigentes retorna 409 na edição cadastral do mentor.

## Conclusão do treinamento

O repositório não possuía uma etapa ou data de conclusão de treinamento. Para não inferir essa condição de `status=ATIVO`, este card adiciona um marco explícito por edição: `treinamento_concluido_em` e `treinamento_concluido_por`, preenchidos pelo servidor.

O Organizador/DEV confirma a conclusão real pelo endpoint abaixo, depois da homologação do resultado. Repetir a confirmação preserva o autor e o instante originais. O Comitê Científico pode consultar o marco, mas não o confirmar nesta política administrativa. O cliente não pode criar ou remover o marco no formulário de atribuição nem no PATCH genérico do hackathon.

| Método | Endpoint | Quem |
|---|---|---|
| GET | `/admin/hackathons/{hackathon_id}/treinamento` | Comitê Científico, Organizador, DEV |
| POST | `/admin/hackathons/{hackathon_id}/treinamento/concluir` | Organizador, DEV |

O marco é uma decisão explícita desta implementação e deve ser conciliado com o futuro módulo de etapas/treinamento na revisão. Este card não cria cursos, presença ou certificação de treinamento.

## Endpoints de mentoria

Todas as rotas exigem conta ativa e JWT. As rotas administrativas exigem Comitê Científico, Organizador ou DEV.

| Método | Endpoint | Operação |
|---|---|---|
| POST | `/admin/equipes/{equipe_id}/mentoria` | Primeira atribuição ou nova atribuição depois de um encerramento; 201 |
| PUT | `/admin/equipes/{equipe_id}/mentoria` | Substitui o vínculo esperado, mantendo histórico; 200 |
| POST | `/admin/equipes/{equipe_id}/mentoria/encerrar` | Encerra logicamente o vínculo esperado; 200 |
| GET | `/admin/equipes/{equipe_id}/mentoria` | Vínculo vigente; 404 quando ausente |
| GET | `/admin/equipes/{equipe_id}/mentoria/historico` | Histórico auditável, mais recente primeiro |
| GET | `/admin/mentores/{mentor_id}/equipes` | Equipes acompanhadas pelo mentor informado |
| GET | `/me/mentoria/equipes` | Equipes do mentor autenticado; não recebe id de outro mentor |
| GET | `/equipes/{equipe_id}/mentor` | Contato e situação do mentor da própria equipe |

Histórico e listas aceitam `limite` (1–100, padrão 50) e `deslocamento` (não negativo). As listas por mentor também aceitam `hackathon_id` e `apenas_vigentes` (padrão `true`). Para listar vínculos já encerrados junto dos vigentes, use `apenas_vigentes=false`.

A consulta da própria equipe segue a autorização existente de `app.services.equipe.consultar`: somente integrantes da equipe e DEV. Outro participante, mentor ou gestor sem vínculo não acessa esse endpoint. Gestores usam as rotas administrativas; mentores usam a listagem própria. Um integrante removido perde o acesso. A resposta de contato não expõe capacidade, outras equipes, senha, aceites nem motivos administrativos.

Primeira atribuição:

```json
{
  "mentor_id": "UUID_DO_MENTOR",
  "motivo": "Distribuição após treinamento"
}
```

O motivo é opcional nessa operação. Se já existe vínculo vigente, retorna 409, inclusive para o mesmo mentor; não repete notificações.

Substituição:

```json
{
  "mentor_id": "UUID_DO_NOVO_MENTOR",
  "atribuicao_atual_id": "UUID_DO_VINCULO_ESPERADO",
  "motivo": "Reorganização do acompanhamento"
}
```

Encerramento recebe `atribuicao_atual_id` e `motivo`. Motivos de substituição e encerramento são obrigatórios, sem texto vazio, até 1000 caracteres. Campos como `ativo`, `hackathon_id` e `atribuido_por` não são aceitos nos formulários de atribuição; seus valores são derivados no servidor.

O vínculo administrativo retorna `id`, `equipe_id`, `hackathon_id`, `mentor_id`, `atribuido_por`, `atribuido_em`, `atribuicao_anterior_id`, `motivo`, `encerrada_em`, `encerrada_por` e `motivo_encerramento`. Não há exclusão física pela API.

Erros: 401 sem autenticação/conta desativada; 403 perfil não autorizado, conta pendente ou consulta de outra equipe; 404 entidade/vínculo inexistente; 409 treinamento pendente, edição encerrada, equipe não aprovada, mentor inelegível, capacidade esgotada ou vínculo esperado desatualizado; 422 formulário, parâmetro ou motivo inválido. Termos não publicados/desatualizados seguem as respostas da BE-S5-10.

## Concorrência e histórico

A transação adquire `FOR UPDATE` na equipe, lê o vínculo vigente e bloqueia os mentores envolvidos na ordem de seus UUIDs. Em seguida reutiliza a validação RN33 e conta os vínculos vigentes do candidato. A trava no mentor também serializa a operação com alteração de capacidade, ativação e desativação da BE-S5-10.

O PostgreSQL garante unicidade por equipe pelo índice parcial `uq_atribuicoes_mentor_equipe_vigente`. A FK composta `(equipe_id, hackathon_id)` impede vínculo com edição diferente da equipe. A referência composta ao predecessor impede encadear histórico de outra equipe; um vínculo tem no máximo um sucessor.

Na substituição, o vínculo anterior recebe instante, autor e motivo de encerramento e é persistido antes de inserir o novo. O novo aponta para o anterior. Reatribuir depois de um encerramento também preserva essa cadeia. Se qualquer regra ou gravação falhar, a transação desfaz o encerramento, o novo vínculo, os eventos e os e-mails.

Dois pedidos de primeira atribuição à mesma equipe produzem um 201 e um 409. Duas equipes disputando a última vaga do mesmo mentor produzem um 201 e um 409. Duas substituições com o mesmo `atribuicao_atual_id` produzem um 200 e um 409. O cliente deve consultar novamente antes de tentar outra substituição. Trocas cruzadas de mentores entre equipes seguem a mesma ordem de bloqueio, evitando deadlock. A capacidade não pode ser excedida para permitir uma troca: mentores já lotados precisam liberar vaga antes.

O encerramento não exige que o mentor ainda esteja ativo nem que a edição permaneça aberta: serve também à manutenção de vínculos após desativação ou término da edição.

O cancelamento da edição em outra transação pode ocorrer depois da checagem de fase da atribuição. Os bloqueios garantem exclusividade/capacidade; não representam uma transação global de encerramento de todas as operações do hackathon.

## RF60 e a dependência da central in-app

Cada atribuição gera avisos para todos os integrantes atuais da equipe e para o mentor, sem duplicar destinatários. Substituições avisam também o mentor anterior; encerramentos avisam a equipe e o mentor do vínculo encerrado. Motivos administrativos, avaliações, notas e senhas não são enviados por e-mail.

O novo tipo `ATRIBUICAO_MENTOR` reutiliza `enfileirar`, os templates texto/HTML, o worker e o acompanhamento do PR #15. A chave `mentoria:{atribuicao_id}:{tipo}:{usuario_id}` evita duplicatas por fato e destinatário. Falha de entrega é tratada pelo worker, sem desfazer a atribuição confirmada. Falha de enfileiramento preserva o evento com `email_enfileirado=false`, permitindo recuperação por uma integração posterior.

A validação identificou uma falha intermitente na reserva da fila: a seleção limitada dentro de `UPDATE ... WHERE id IN (...)` podia ser reexecutada em planos com nested loop e exceder o limite do lote. A seleção agora usa uma CTE `MATERIALIZED`, mantendo `FOR UPDATE SKIP LOCKED`, com ordenação explícita do retorno. A regressão reproduz o excesso no código anterior com estatísticas desatualizadas e um plano genérico alternativo, e verifica limite, ordem e contagem de tentativas.

**A central genérica in-app ainda não está integrada nesta base.** O único endpoint existente, `GET /me/notificacoes`, é específico de resultado. Este card não altera seu contrato nem registra uma publicação fictícia. A tabela `eventos_notificacao_mentoria` guarda, na mesma transação da atribuição, cada destinatário, o vínculo, o tipo (`ATRIBUIDA`, `SUBSTITUIDA`, `ENCERRADA`), a mensagem e a situação de enfileiramento do e-mail. `publicado_na_plataforma_em=NULL` significa publicação pendente.

O adaptador `app.controllers.atribuicao_mentor.eventos_pendentes_plataforma()` oferece leitura com `FOR UPDATE SKIP LOCKED`. O consumidor da central deve criar a notificação usando o id do evento como chave de deduplicação e preencher `publicado_na_plataforma_em` na **mesma transação**; falhas devem desfazer ambos. O teste cobre essa leitura e a retirada de eventos já publicados. Publicação in-app e sua interface ficam dependentes da integração da central (BE-S5-04).

A gravação do evento durável é obrigatória: se falhar, toda a atribuição é desfeita. O enfileiramento de e-mail mantém a política de tolerância a falhas do PR #15. Os avisos desta entrega são de mudança de mentoria; o futuro chat continua sem gerar e-mails (RN32).

## Preparação do chat

`atribuicoes_mentor.id` é uma referência estável para a futura conversa, com FKs para equipe, edição e mentor e vínculo com o predecessor. Mensagens futuras podem referenciar esse id sem misturar conversas após substituições.

O chat deverá verificar no servidor o vínculo vigente, a atividade do mentor e a participação atual do integrante na equipe para autorizar novas mensagens. Histórico de atribuição não equivale a autorização atual de chat. Mensagens, anexos, canais e permissões históricas de chat não são implementados neste card.

## Migration, arquivos e validação

Nova migration `V202611121300__atribuicao_mentores.sql`: marco de treinamento, atribuições com índice parcial/FKs/checks, eventos duráveis e novo tipo de e-mail. Migrations anteriores não foram modificadas. Aplique Flyway antes de iniciar a API atualizada.

| Grupo | Arquivos |
|---|---|
| Atribuição | `app/models/atribuicao_mentor.py`, `app/controllers/atribuicao_mentor.py`, `app/schemas/atribuicao_mentor.py`, `app/services/atribuicao_mentor.py`, `app/exceptions/atribuicao_mentor.py`, `app/views/atribuicoes_mentor.py` |
| RF60 | `app/models/evento_mentoria.py`, `app/services/notificacao_mentoria.py`, `app/services/email_template.py`, `app/controllers/email_outbox.py`, `app/templates/emails/atribuicao_mentor.txt`, `app/templates/emails/atribuicao_mentor.html` |
| Integração | `app/models/hackathon.py`, `app/services/mentor.py`, `app/views/mentores.py`, `app/const/enums.py`, `app/models/__init__.py`, `app/views/__init__.py`, `app/__init__.py` |
| Migration | `migrations/V202611121300__atribuicao_mentores.sql` |
| Testes | `tests/test_atribuicoes_mentor.py`, `tests/test_email_templates.py`, `tests/test_email_envio.py` |
| Documentação | `README.md`, `docs/atribuicao-mentores.md`, `docs/mentores.md`, `docs/emails.md`, `docs/banco-de-dados.md`, `docs/api-contratos.md` |

Os testes usam PostgreSQL exclusivo com sufixo `_test`, sem envio SMTP real. Cobrem atribuição, treinamento, aprovação, RN33 real, termos por edição, capacidade global e sua redução, isolamento, histórico, encerramento, trocas concorrentes/cruzadas, última vaga, restrições PostgreSQL, rollback com avisos, entrega pelo worker e eventos pendentes para a central.

Validação concluída: Flyway aplicado no banco exclusivo de testes; `ruff check .` e `ruff format --check .` aprovados. A rodada de worker, atribuições e cadastro/ativação de mentores passou com **178 testes**; a suíte completa passou com **1317 testes**, incluindo a nova regressão da reserva. A rodada inicial de atribuições, templates e migrations teve **119 testes aprovados**. Permanecem os avisos de depreciação de Starlette da infraestrutura existente. A publicação in-app continua dependente da central, conforme descrito acima.

```sh
docker compose run --rm flyway_test
docker compose run --rm --no-deps app ruff check .
docker compose run --rm --no-deps app ruff format --check .
docker compose run --rm --no-deps app python -m pytest tests/test_atribuicoes_mentor.py
docker compose run --rm --no-deps app python -m pytest
```
