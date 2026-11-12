[← Voltar ao README](../README.md)

# Cadastro e ativação de mentores — BE-S5-10

RF37, RN24 e RN33. O Comitê Científico cadastra e gerencia mentores; Organizador atua como exceção administrativa e DEV mantém o acesso previsto no projeto.

## Análise e decisões

- Base: `origin/main`, incluindo o [PR #15](https://github.com/Hackathon-UFPA/hackathon_backend/pull/15). Reutilizados o serviço `enfileirar`, o template `DEFINICAO_SENHA`, o worker e o acompanhamento da fila. Nenhum novo provedor ou worker foi criado.
- `Usuario` já possui `nome`, `email`, `empresa_parceira`, `area_atuacao` e `max_equipes`. Empresa de origem continua um texto do perfil, conforme o modelo existente; este card não cria um catálogo independente de empresas.
- Reutilizados Argon2 e a política de senha, o índice de e-mail sem diferenciação de maiúsculas, as permissões existentes e as tabelas de termos e aceites com versão e data do servidor.
- A migration inicial adiciona os marcos de conclusão e a tabela de convites. A revisão usa `V202611121200__revisao_convites_mentor.sql` para vincular convites à edição, registrar enfileiramento e permitir cancelar mensagens revogadas. Migrations anteriores permanecem intactas.
- O documento completo da Sprint 4 não foi localizado no repositório nem nas buscas do Drive conectado. Os critérios implementados são os RF37/RN24/RN33 detalhados no card e os contratos já presentes no projeto.

## Estados

| Estado | `ativo` | `mentor_perfil_concluido_em` / `mentor_ativado_em` |
|---|---|---|
| Aguardando o próprio mentor | `false` | `null` |
| Mentor ativado pela RN33 | `true` | Preenchidos pelo servidor |
| Desativado administrativamente após onboarding | `false` | Preservados |

`situacao_conta=PENDENTE` continua sendo a pendência de comprovante dos participantes (RN25). O mentor é criado com `situacao_conta=ATIVA`, mas **`ativo=false`**, sem senha e sem acesso autenticado. A interface identifica o onboarding pendente pelos marcos de conclusão ausentes. Nenhum comprovante acadêmico ou profissional é criado ou exigido.

## Endpoints

Todas as rotas `/admin/mentores` exigem Comitê Científico, Organizador ou DEV, autenticado e ativo.

| Método | Rota | Operação |
|---|---|---|
| POST | `/admin/mentores` | Cadastro pendente e convite, 201 |
| GET | `/admin/mentores` | Lista com filtro `ativo`, `limite` 1–100 e `deslocamento` |
| GET | `/admin/mentores/{id}` | Consulta apenas usuários com papel MENTOR |
| PATCH | `/admin/mentores/{id}` | Edita os cinco campos cadastrais |
| POST | `/admin/mentores/{id}/convite` | Convite para a edição informada, inclusive para mentor ativo; substitui os anteriores daquela edição |
| GET | `/admin/mentores/{id}/convites` | Histórico e pendências de enfileiramento/entrega, sem tokens; paginação `limite` e `deslocamento` |
| POST | `/admin/mentores/{id}/ativar` | Reativação administrativa; exige RN33 já concluída e termos vigentes aceitos |
| POST | `/admin/mentores/{id}/desativar` | Desativação lógica e revogação dos convites pendentes |
| POST | `/mentores/convite/consultar` | Sem login; token no corpo, retorna perfil e termos da edição |
| POST | `/mentores/ativacao` | Sem login; o próprio destinatário conclui a RN33 com seu token |

Cadastro:

```json
{
  "nome": "Maria da Silva",
  "email": "maria@empresa.com",
  "empresa_parceira": "Empresa parceira",
  "area_atuacao": "Ciência de dados",
  "max_equipes": 2,
  "hackathon_id": "UUID_DA_EDICAO"
}
```

Nome, empresa e área são obrigatórios, sem texto vazio, com espaços externos removidos e limite de 255 caracteres. E-mail deve ser válido e único entre todos os perfis. Capacidade deve ser um inteiro JSON de 1 a 32767, limite do `smallint` existente; booleanos, números fracionários e strings são recusados. Campos extras e alterações de papel, senha ou `ativo` pelo PATCH são recusados.

`hackathon_id` é obrigatório no cadastro e deve identificar uma edição existente; não há escolha automática da edição mais recente. `POST /admin/usuarios` com `papel=MENTOR` passa pelo mesmo serviço, exige os cinco campos e `hackathon_id`, e não permite senha inicial definida pelo administrador. Os demais perfis continuam exigindo senha inicial e nascendo ativos. O script de bootstrap não cria mentores: eles devem passar pela API administrativa.

## Fluxo para o frontend

1. O administrador cadastra o mentor. A conta, o hash do convite e o e-mail no outbox são gravados na mesma transação. O provedor envia depois, pelo worker existente.
2. O e-mail aponta para `${FRONTEND_URL}/mentores/ativacao#token=...&hackathon_id=...`. O fragmento evita mandar o token na URL HTTP ao servidor web. A interface deve ler e remover o fragmento do navegador e transmitir o token somente no corpo das requisições; não deve registrá-lo em analytics ou logs.
3. O frontend envia `{"token":"...","hackathon_id":"UUID_DO_LINK"}` a `/mentores/convite/consultar`. A API compara a edição informada com a persistida no convite: divergência retorna **409**, mesmo se ambas as edições existirem e tiverem termos válidos. A resposta informa `hackathon_id`, o perfil, os termos **da edição vinculada** e `senha_necessaria`. A consulta não consome o token. O mesmo contrato atende clientes distintos, sem depender de uma edição global implícita.
4. Após leitura e aceite explícito dos dois documentos, envia `/mentores/ativacao`:

```json
{
  "token": "TOKEN_RECEBIDO_POR_EMAIL",
  "hackathon_id": "UUID_DA_EDICAO",
  "nome": "Maria da Silva",
  "empresa_parceira": "Empresa parceira",
  "area_atuacao": "Ciência de dados",
  "senha": "MinhaSenha123",
  "termos_ids": ["UUID_REGULAMENTO_VIGENTE", "UUID_CONSENTIMENTO_VIGENTE"]
}
```

5. A API valida token, igualdade entre a edição informada e a vinculada ao convite, perfil, senha quando ausente e versões vigentes dos dois termos **da edição persistida**; registra os aceites para o usuário do convite, os marcos de conclusão e o consumo do token; então ativa a conta. Termos de outra edição são recusados com 409. Não recebe `usuario_id`, `ativo`, `papel` nem `max_equipes` neste formulário.
6. O mentor entra normalmente por `/auth/login`. Antes da conclusão, login é recusado. Mentores legados ativos sem os marcos RN33 também são recusados pelas dependências das rotas de negócio.

Token aleatório de 256 bits, SHA-256 no banco, validade configurável em `MENTOR_CONVITE_MINUTOS` (padrão 1440, 24 horas). Token inválido, expirado, revogado ou utilizado retorna 400 com a mesma mensagem. Senha ausente quando necessária retorna 422; senha é armazenada apenas como hash Argon2. Uma senha existente é preservada quando omitida ao renovar o onboarding; se o destinatário fornecer uma nova senha, ela substitui a anterior. O token não é um JWT de login e não autentica outras rotas.

Ativação inválida não consome o convite nem deixa aceites parciais. Uma trava de linha no mentor serializa ativação, edição, reenvio e desativação. Dois consumos simultâneos do mesmo convite resultam em um sucesso e uma rejeição.

## Administração e recuperação

`POST /admin/mentores/{id}/convite` recebe `{"hackathon_id":"UUID_DA_EDICAO"}`. Pode emitir convites para novas edições de um mentor já ativo. Aceites e convites de outras edições permanecem válidos; reemitir na edição A não revoga um convite da edição B. O mentor só fica elegível para uma edição depois de aceitar os respectivos termos vigentes, conforme `validar_elegibilidade`. Enviar outro convite não desativa uma conta já ativa.

`POST /admin/mentores/{id}/ativar` recebe `{"hackathon_id":"UUID"}`. Recusa cadastro pendente, perfil incompleto, senha ausente e falta de aceites vigentes. O administrador não pode aceitar os termos pelo mentor. Para desativado que precisa aceitar novas versões, envie outro convite; o mentor completa o fluxo e pode manter sua senha existente.

Desativar bloqueia login, tokens de acesso existentes e elegibilidade para novas atribuições. Preserva cadastro, senha, aceites e marcos. Também revoga convites em aberto: um link anterior à desativação não pode reativar a conta. Um novo convite administrativo autoriza novamente o onboarding.

Alterar e-mail exige `hackathon_id` no PATCH para identificar a edição do novo convite. A mudança revoga os convites de todas as edições e o acesso, limpa a senha e os marcos atuais de onboarding e envia novo convite ao endereço atualizado, que precisa comprovar sua posse e concluir a RN33. Aceites históricos permanecem no banco. Não existe exclusão física pela API.

Mentores legados não são ativados nem regularizados automaticamente pela migration. Para cumprir a RN33, o gestor deve desativá-los e enviar um convite.

Conforme o PR #15, falha de enfileiramento não desfaz o cadastro principal. O convite registra `email_enfileirado=false` e a conta nova continua inativa. O gestor pode consultar `GET /admin/mentores/{id}/convites`, autorizado também para Comitê Científico, e emitir outro convite após corrigir a causa. A resposta inclui somente id, edição, datas, `email_enfileirado`, `status_email`, `cancelado_em` e `pendencia_administrativa`. Esta última é verdadeira para convite aberto sem enfileiramento, sem registro de e-mail, com falha de entrega ou expirado. Convites encerrados não geram essa pendência. A consulta tem `limite` de 1 a 100 (padrão 50) e `deslocamento` não negativo.

Falhas de entrega continuam sob as tentativas do worker e também podem ser acompanhadas em `/admin/emails` por Organizador/DEV. Mensagens com `cancelado_em` não podem ser reenviadas por essa rota (409); deve ser emitido um novo convite. Os logs de enfileiramento/entrega de convites usam identificadores e mensagens sanitizadas, sem traceback que possa expor parâmetros SQL com links secretos. Não há tokens, hashes, corpos de e-mail ou senhas na consulta administrativa. O token em claro existe apenas no corpo do e-mail, eliminado do outbox após envio ou cancelamento.

## Revogação e concorrência com o worker

Reemitir o convite cancela as mensagens não enviadas dos convites anteriores **da mesma edição**, inclusive as reservadas (`ENVIANDO`). Desativação e alteração de e-mail cancelam os convites de todas as edições. A revogação e o novo outbox usam a mesma transação; se ela falhar, o convite anterior e seu e-mail continuam válidos. Não são apagadas linhas do histórico.

Mensagens canceladas ficam em `FALHA`, com `cancelado_em`, reserva liberada e corpos eliminados; não entram novamente na reserva. O worker confirma a reserva como no PR #15, mas antes de enviar um convite de mentor obtém `FOR UPDATE` no respectivo e-mail e verifica cancelamento, status e tentativa. A trava permanece até registrar o resultado do provedor. Assim, uma cópia já reservada em memória é descartada se o reenvio revogou o convite antes de a entrega começar. Outros tipos de e-mail mantêm o fluxo existente.

Se o envio ao provedor já começou, a revogação aguarda essa transação terminar. Uma mensagem já entregue não pode ser recolhida; seu registro `ENVIADO` permanece intacto, e o link anterior deixa de funcionar quando a revogação é confirmada. Cancelamento não é tratado como erro do provedor nem causa nova tentativa automática. A garantia de entrega do PR #15 continua sendo pelo menos uma vez.

Convites legados sem edição confiável são preservados e revogados pela migration de revisão; seus e-mails ainda não enviados são cancelados. A edição não é inferida a partir de uma seleção global. Para renovar, o gestor informa explicitamente a edição. Na atualização, encerre os workers antigos antes de aplicar a migration e iniciar o código novo, pois workers antigos não verificam cancelamento de cópias já reservadas.

## Integração BE-S5-11 e limites

`app.services.mentor.validar_elegibilidade(db, mentor_id, hackathon_id)` verifica papel, ativo administrativo, conclusão do perfil, senha, capacidade positiva e aceites vigentes para a edição. Mantém `FOR UPDATE` no mentor até o commit da transação chamadora. Não usa a comprovação acadêmica.

A atribuição ainda não possui tabela no projeto. O BE-S5-11 deve, na **mesma transação**:

1. Chamar a verificação de elegibilidade e manter a trava do mentor.
2. Contar atribuições ativas e rejeitar quando a quantidade atingir `mentor.max_equipes`.
3. Garantir no banco uma única atribuição ativa por equipe, inclusive em concorrência.
4. Inserir a atribuição e confirmar a transação.

Não foram implementados atribuição, contagem fictícia de equipes nem frontend. Não há envio SMTP real nos testes: a integração usa o provedor em memória e o worker do PR #15.

## Validação local

```sh
docker compose run --rm flyway_test
docker compose run --rm --no-deps app ruff check app tests
docker compose run --rm --no-deps app ruff format --check app tests
docker compose run --rm --no-deps app python -m pytest
```

Os testes usam exclusivamente o banco com sufixo `_test`, sem worker automático. `tests/test_mentores.py` cobre validações, todos os perfis administrativos, cadastro e edição, sigilo de token e senha, outbox e entrega, atomicidade, termos vigentes, ativação simultânea, revogação de convites, desativação e elegibilidade. `tests/test_permissoes.py` preserva a cobertura dos demais perfis e atualiza as expectativas de mentores para RN33.

A revisão acrescenta cobertura com duas edições válidas e termos diferentes, clientes distintos, aceites em novas edições, dois convites antes do worker, cancelamento após a reserva, envio em andamento, preservação de mensagens enviadas, rollback de reenvio, falha de enfileiramento/entrega com recuperação e contratos OpenAPI sem exposição de segredos.

## Arquivos da revisão técnica

Validação da revisão em 12/11/2026: Flyway aplicado no banco exclusivo de testes, `ruff check .` e `ruff format --check .` aprovados; suíte completa com **1268 testes aprovados** e rodada específica final de mentores com **112 testes aprovados**. Permanecem os avisos de depreciação de Starlette da infraestrutura existente.

| Grupo | Arquivos |
|---|---|
| Convites de mentor | `app/models/convite_mentor.py`, `app/controllers/mentor.py`, `app/services/mentor.py`, `app/schemas/mentor.py`, `app/views/mentores.py` |
| Cadastro genérico | `app/schemas/auth.py`, `app/services/usuario.py`, `app/views/usuarios.py` |
| Outbox e worker | `app/models/email_outbox.py`, `app/controllers/email_outbox.py`, `app/services/email.py`, `app/services/email_envio.py`, `app/exceptions/email.py`, `app/schemas/email.py`, `app/views/emails.py` |
| Migration nova | `migrations/V202611121200__revisao_convites_mentor.sql` |
| Testes | `tests/conftest.py`, `tests/test_mentores.py`, `tests/test_permissoes.py` |
| Documentação | `docs/mentores.md`, `docs/autenticacao.md`, `docs/emails.md` |
