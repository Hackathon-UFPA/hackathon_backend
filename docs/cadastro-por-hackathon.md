# Cadastro, autodeclaração e comprovantes por hackathon — BE-S6-14

A conta de participante é única na plataforma. As declarações e os documentos pertencem a uma
edição, mesmo quando duas organizações mantêm inscrições abertas simultaneamente.

## Inspeção e escopo

A `main` local e a remota foram verificadas em `93777ed`, merge do
[PR #26](https://github.com/Hackathon-UFPA/hackathon_backend/pull/26). Seus commits `6343e8c` e
`e4e9634` introduziram organizações e isolamento administrativo. O fluxo de convite veio do
PR #25 (`1f99402`, com a correção `18dfd77` para o tipo do comprovante). Os contratos desta entrega
foram implementados exclusivamente na branch `fix/be-s6-14-cadastro-por-hackathon`.

A busca de chamadas de `get_hackathon_com_inscricoes()` identificou quatro operações implícitas:
cadastro público, consulta da declaração, alteração da declaração e envio de comprovante sem ID.
Antes, todas podiam selecionar a edição com início mais recente. A resolução agora é comum aos
três serviços e o próprio seletor legado rejeita ambiguidade. Datas de início do evento não
determinam qual edição recebe os dados.

As consultas de declaração, histórico, tipo indicado pelo líder e comprovante já recebem o par
usuário/edição. A homologação também já usa comprovantes por edição e tipo. Essas regras foram
preservadas e verificadas com testes de integração. No cadastro por convite, a edição continua
vindo de `convite → equipe → hackathon`, sem seleção global.

## Contratos antigos e novos

| Operação | Antes | Agora |
|---|---|---|
| `POST /auth/cadastro` | Corpo sem seleção de edição; comprovante na edição aberta mais recente | Campo opcional `hackathon_id` no JSON; comprovante somente nessa edição |
| `GET /me/autodeclaracao` | Seleção global entre inscrições abertas | `?hackathon_id={uuid}`; permite consultar o próprio histórico de edições encerradas, finalizadas ou canceladas |
| `PUT /me/autodeclaracao` | Seleção global entre inscrições abertas | Mesmo parâmetro de consulta do GET; corpo original preservado; exige inscrições abertas na edição |
| `POST /comprovantes` | ID opcional no JSON; omissão escolhia edição aberta mais recente | Campo existente preservado; omissão só funciona com uma edição elegível |
| `POST /auth/cadastro/convite` | Token determina equipe e edição | Contrato preservado; comprovante opcional usa a edição da equipe e o tipo indicado no convite; `hackathon_id` no corpo continua dando 422 |
| `GET /comprovantes/meus` | Histórico da conta em todas as edições | Contrato preservado; cada item informa `hackathon_id`, para filtrar na interface |

**Compatibilidade sem ID:** zero edições elegíveis retorna 409 com a mensagem existente; uma usa
essa única edição; duas ou mais retornam 409 com
`Há mais de um hackathon com inscrições abertas. Informe hackathon_id para selecionar a edição.`
O critério é global entre organizações, considerando **status e período**, inclusive datas nulas
conforme a regra RN06 existente. Não se deduz edição pela conta, pelo comprovante anterior,
pelo convite associado ou pela data de início do evento. Um ID explícito nunca faz fallback.

As respostas de sucesso mantêm os formatos anteriores: 201 no cadastro/envio de documento e 200
na consulta/alteração da declaração. `null` no campo opcional equivale à omissão.

### Requisições

Cadastro público, sem autenticação:

```http
POST /auth/cadastro
Content-Type: application/json

{
  "hackathon_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "nome": "Ana Souza",
  "email": "ana@example.com",
  "senha": "segredo123",
  "instituicao": "UFPA",
  "curso": "Sistemas de Informação",
  "periodo": 5,
  "comprovante_url": "https://example.com/comprovante.pdf"
}
```

Autodeclaração, com conta ativa ou pendente (também aceita DEV):

```http
PUT /me/autodeclaracao?hackathon_id=3fa85f64-5717-4562-b3fc-2c963f66afa6
Authorization: Bearer <token>
Content-Type: application/json

{"tipo":"ESTUDANTE","instituicao":"UFPA","curso":"Sistemas de Informação","periodo":5}
```

```http
GET /me/autodeclaracao?hackathon_id=3fa85f64-5717-4562-b3fc-2c963f66afa6
Authorization: Bearer <token>
```

Envio de documento, com a mesma conta, para a edição selecionada:

```http
POST /comprovantes
Authorization: Bearer <token>
Content-Type: application/json

{"hackathon_id":"3fa85f64-5717-4562-b3fc-2c963f66afa6","arquivo_url":"https://example.com/comprovante.pdf"}
```

Para outra edição, troque o ID nos pedidos autenticados. Repetir cadastro com o mesmo e-mail,
inclusive mudando maiúsculas ou edição, continua retornando 409. Não se cria outra conta.

### Erros e autorização

| Código | Situação |
|---|---|
| 401 | Token ausente/inválido nas operações autenticadas |
| 403 | Papel sem permissão para declarar ou validar; conferente de outra organização |
| 404 | ID de hackathon inexistente; rascunho na consulta da declaração; comprovante inexistente na decisão administrativa |
| 409 | Edição explícita fora do status `INSCRICOES` (inclusive rascunho/cancelada), período futuro/encerrado nas escritas; nenhuma ou várias edições elegíveis sem ID; e-mail duplicado; comprovante ativo do mesmo usuário/edição/tipo ou já decidido |
| 422 | ID sem formato UUID, corpo inválido ou campo extra no corpo da autodeclaração |

O usuário sempre vem do token. O ID da edição não permite consultar declarações ou documentos de
terceiros. Rascunhos continuam privados na consulta. A declaração só aceita `hackathon_id` na
query; enviá-lo no corpo continua dando 422. O comprovante preserva o comportamento anterior de
ignorar campos extras; nenhum campo extra altera o dono do documento.

A fila e as decisões administrativas continuam restritas à organização dona do hackathon;
DEV mantém sua exceção técnica. `GET /comprovantes/meus` traz só os documentos do usuário logado.
O resumo da declaração não expõe a URL privada do arquivo. Uma aprovação ativa a conta global,
mas só comprova o vínculo na edição e no tipo do documento, reavaliando somente a equipe dessa
edição. Uma declaração divergente também só afeta a equipe da edição solicitada.

## Transações e concorrência

O cadastro público faz rollback explícito de conta, comprovante, associação de convites,
notificações e confirmação de e-mail se uma etapa falhar. O índice único de e-mail sem distinção
de maiúsculas continua impedindo contas duplicadas em cadastros concorrentes entre edições.
O índice parcial de comprovantes continua limitando documentos pendentes/aprovados por
usuário/edição/tipo. As declarações continuam serializadas pela trava do usuário: repetir os
mesmos dados na mesma edição é idempotente; os mesmos dados em outra edição são outra declaração.
O link de convite continua de uso único e transacional.

## Ajustes necessários no frontend

O frontend foi inspecionado somente para leitura na `main` em
[`441cfdb`](https://github.com/Hackathon-UFPA/hackathon_frontend/tree/441cfdbd82bfc24228236228c077e852372be65e).
Nenhum arquivo desse repositório foi alterado.

| Local | Ajuste |
|---|---|
| `lib/api.ts` | Acrescentar `hackathon_id?: string` a `CadastroRequest`, usado por `auth.cadastrar`. `comprovantes.enviar(hackathon_id, arquivo_url)` já envia o ID; `comprovantes.reenviar(arquivo_url)` e `moduloCApi.enviarNovoComprovante(url)` precisam recebê-lo e repassá-lo. Tratar 404, 409 e 422 sem trocar ou omitir o ID como recuperação |
| `lib/api-participante.ts` | Alterar `autodeclaracao.obter()` para receber a edição e usar `query: { hackathon_id }`. Fazer o mesmo em `autodeclaracao.declarar(dados)`, mantendo o corpo de `dados` |
| `app/login/page.tsx` | O cadastro público está na aba de cadastro deste arquivo, na chamada `auth.cadastrar`. Preservar a edição da navegação/vitrine e enviá-la no corpo; hoje `next` mantém `/equipe?hackathon_id=...` para a navegação, mas o payload omite o ID. Para conta existente, usar login e envio de documento nessa edição |
| `app/perfil/page.tsx` | O componente `Vinculo` chama GET/PUT sem edição. Receber uma seleção explícita, recarregar e enviar para ela. O tratamento atual considera todo 409 como ausência de edição aberta: precisa distinguir e mostrar também a mensagem de ambiguidade, sem ocultá-la |
| `components/modulo-c/ComprovanteCard.tsx` | Já mantém `hackathonId` e chama `moduloCApi.enviarComprovante(hackathonId, url)`, que envia o ID. Preservar esse caminho e a edição em reenvios; não reutilizar aprovação de outra edição |
| Estado/cache da interface | Incluir usuário e hackathon na chave; ao trocar de edição, recarregar os dados e evitar exibir respostas atrasadas da seleção anterior |
| Histórico e comprovantes próprios | Permitir GET explícito em edição encerrada e manter edição histórica em consulta; filtrar `GET /comprovantes/meus` pelo `hackathon_id` de cada item |
| `app/cadastro/page.tsx` | Esta página é o cadastro por convite (`#convite=`), não o cadastro público. Preservar token e contrato existentes; o servidor determina a edição da equipe. Não acrescentar `hackathon_id` ao corpo |

Referências inspecionadas: [cliente HTTP](https://github.com/Hackathon-UFPA/hackathon_frontend/blob/441cfdbd82bfc24228236228c077e852372be65e/lib/api.ts),
[cliente participante](https://github.com/Hackathon-UFPA/hackathon_frontend/blob/441cfdbd82bfc24228236228c077e852372be65e/lib/api-participante.ts),
[cadastro público](https://github.com/Hackathon-UFPA/hackathon_frontend/blob/441cfdbd82bfc24228236228c077e852372be65e/app/login/page.tsx),
[perfil](https://github.com/Hackathon-UFPA/hackathon_frontend/blob/441cfdbd82bfc24228236228c077e852372be65e/app/perfil/page.tsx) e
[formulário de comprovante](https://github.com/Hackathon-UFPA/hackathon_frontend/blob/441cfdbd82bfc24228236228c077e852372be65e/components/modulo-c/ComprovanteCard.tsx).

## Banco e decisões de produto

**Não é necessária migration.** As tabelas já têm `hackathon_id`; os índices existentes cobrem
unicidade do e-mail e comprovante por usuário/edição/tipo. Nenhuma migration aplicada foi editada.
Esta entrega não reatribui documentos antigos que possam ter sido enviados à edição errada.
Uma eventual correção desses dados requer identificar casos concretos e autorização específica.

Continuam pendentes de validação do Squad 1, conforme BE-S5-13 e documentação da BE-S5-03:
elegibilidade de profissionais e mistos, documento profissional e responsáveis pela conferência
(Q25), obrigatoriedade da autodeclaração e tratamento definitivo da divergência de tipo.
Os padrões `exige_autodeclaracao=false`, `exige_comprovante_estudante=true` e
`exige_comprovante_profissional=true`, as categorias e os termos foram preservados.
O comprovante público inicial continua sendo `ESTUDANTE`; no convite, usa o tipo indicado pelo
líder. A consulta histórica permite ler, sem ampliar o prazo de alteração.

## Validação direcionada

A política atual exige testes com caminhos específicos e Ruff somente nos arquivos Python
modificados. As rodadas finais concluídas foram:

| Seleção | Motivo | Aprovados | Reprovados |
|---|---|---:|---:|
| `tests/test_auth.py`, `tests/test_autodeclaracao.py`, `tests/test_comprovantes.py`, `tests/test_hackathon.py` | Serviços, contratos e seletor alterados; compatibilidade existente | 148 | 0 |
| `tests/test_cadastro_por_hackathon.py`, `tests/test_cadastro_equipe_integrantes.py`, `tests/test_organizacoes.py` | Isolamento entre edições/organizações, convites e homologação | 106 | 0 |
| `tests/test_cadastro_por_hackathon.py -k 'falha_no_cadastro or sem_edicoes_abertas or email_existente_nao or consulta_historica_respeita_prazo'` | Somente casos acrescentados ou alterados após a rodada anterior | 6 | 0 |

A última seleção deixou 30 casos de fora porque já tinham passado e não foram alterados.
As contagens por rodada incluem reexecução dos três casos de rollback que receberam novas
asserções; não são um total de casos distintos.

`ruff check` e `ruff format --check` passaram nos **18 arquivos Python modificados**.
`git diff --check` também passou. Os testes emitiram avisos de depreciação de Starlette
(`httpx` e a constante de status 422), sem falhas nas rodadas finais.

A suíte completa foi iniciada conforme a solicitação inicial e **interrompida quando a política
de execução foi atualizada**. Não há resultado conclusivo dessa execução e ela não será repetida
neste ambiente. A validação completa fica para o GitHub Actions após abertura autorizada do PR;
nenhum PR foi aberto nesta entrega. Módulos fora do escopo não receberam novas rodadas de testes.

O risco residual é a regressão em consumidores indiretos ainda não validada pelo CI. A mudança
intencional de compatibilidade é o 409 para clientes sem ID diante de várias edições elegíveis.
Nenhuma regra de autenticação, categoria, termo ou política de homologação foi substituída.

## Arquivos da entrega

- Resolução e erro de ambiguidade: `app/controllers/hackathon.py`,
  `app/exceptions/hackathon.py` e o novo `app/services/edicao_participante.py`.
- Serviços dos fluxos: `app/services/auth.py`, `app/services/autodeclaracao.py` e
  `app/services/comprovante_vinculo.py`.
- Schemas e OpenAPI: `app/schemas/auth.py`, `app/schemas/comprovante_vinculo.py`,
  `app/views/auth.py`, `app/views/autodeclaracao.py` e `app/views/comprovantes.py`.
- Testes: novo `tests/test_cadastro_por_hackathon.py`, `tests/conftest.py`,
  `tests/test_auth.py`, `tests/test_autodeclaracao.py`, `tests/test_comprovantes.py`,
  `tests/test_hackathon.py` e `tests/test_cadastro_equipe_integrantes.py`.
- Documentação: `README.md`, este documento, `docs/api-contratos.md`, `docs/autenticacao.md`,
  `docs/autodeclaracao-e-comprovantes.md`, `docs/inscricao-e-homologacao.md` e
  `docs/cadastro-equipe-integrantes.md`.

[← Voltar ao README](../README.md)
