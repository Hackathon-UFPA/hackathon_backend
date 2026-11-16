[← Voltar ao README](../README.md)

# Central de notificações in-app — BE-S5-04

RF19, RF22, RF28, RF33, RF38, RF53, RF60, RF61. Generaliza o aviso do resultado ([RF33](notificacoes-e-somente-leitura.md)) em uma central de eventos dentro da plataforma. O e-mail continua na fila de [E-mails](emails.md), sem mudança: a central é só o canal in-app.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `GET /me/notificacoes` | Usuário autenticado e ativo | Lista as próprias notificações (`lida`, `tipo`, `limite`, `deslocamento`) |
| `GET /me/notificacoes/nao-lidas/contagem` | idem | `{"nao_lidas": N}` |
| `POST /me/notificacoes/{notificacao_id}/lida` | idem | Marca uma como lida (idempotente) |
| `POST /me/notificacoes/lidas` | idem | Marca todas como lidas e devolve `{"marcadas": N}` |

Erros: 401 sem token ou token inválido; 403 conta pendente; 404 notificação inexistente **ou de outra pessoa** (nunca 403, para não revelar que existe); 422 parâmetro inválido.

## Privacidade

Toda consulta e atualização filtra por `usuario_id` do token. Não há rota de listagem administrativa, e o DEV também só vê as próprias. Marcar a notificação de outro usuário responde 404 com a mesma mensagem de uma inexistente, e não altera nada.

## Tipos

Enum `tipo_notificacao` (Postgres, como `tipo_email`). Adicionar um tipo é uma migration com `ALTER TYPE ... ADD VALUE`.

| Tipo | Quando | Quem recebe | Chave de idempotência |
|------|--------|-------------|-----------------------|
| `CONVITE` | Convite criado (RF19) | Convidado, **só se já tem conta** | `convite:{convite_id}` |
| `ACEITE` | Convite aceito ou recusado; `dados.resposta` = `ACEITO` ou `RECUSADO` | Líder que convidou | `convite-resposta:{convite_id}:{status}` |
| `INSCRICAO` | Inscrição concluída (`dados.evento = CONCLUIDA`) e equipe homologada (`HOMOLOGADA`) (RF22, RF23) | Todos os integrantes | `inscricao:{protocolo_id}` e `equipe_homologada:{equipe_id}:{homologada_em}` |
| `PROPOSTA` | Proposta enviada (RF28) | Líder | `protocolo_proposta:{protocolo_id}` |
| `RESULTADO` | Resultado homologado (RF33) | Todos os integrantes de cada equipe com proposta | `resultado:{homologacao_id}:{equipe_id}` |
| `MENTOR` | Atribuição, substituição ou encerramento (RF38, RF53) | Equipe, mentor e mentor anterior | `mentoria:{atribuicao_id}:{tipo}` |
| `CHAT` | **Sem produtor ainda** (BE-S6-06) | — | a definir no produtor |
| `PRAZO` | **Sem produtor ainda** (BE-S7-06/07) | — | a definir no produtor |

Convidado sem conta recebe só o e-mail. A notificação não é retroativa se a conta for criada depois.

## Formato da resposta e compatibilidade com o RF33

`GET /me/notificacoes` devolve uma **lista pura** (o mesmo formato de antes). O consumidor distingue os itens pelo campo `tipo` (união discriminada no OpenAPI).

Campos comuns: `id`, `notificacao_id`, `tipo`, `titulo`, `mensagem`, `dados` (objeto opcional, varia por tipo), `referencia` (`{tipo, id}` do objeto de origem, opcional), `criado_em`, `lida_em` (nulo se não lida).

O item `RESULTADO` mantém **todos** os campos do RF33 com o mesmo nome e significado: `id` (o da linha de `notificacoes_resultado`, preservado), `hackathon_id`, `equipe_id`, `submissao_id`, `aprovada`, `mensagem`, `canal`, `status_envio`, `enviado_em`, `erro`, `criado_em` e `pareceres`.

**Única mudança de contrato, aditiva:** todo item ganha `notificacao_id` (o id na central, usado nas rotas de leitura) e os itens de resultado ganham também `tipo`, `titulo`, `dados`, `referencia` e `lida_em`. Nos itens de resultado, `id` e `notificacao_id` são diferentes; nos demais, são iguais. Usar o `id` do RF33 na rota de leitura dá 404.

Clientes antigos que ignoram campos desconhecidos continuam funcionando. Eles passam a receber, na mesma lista, itens de outros tipos, sem `aprovada`, `canal` e `pareceres`.

## Paginação

`limite` (1 a 100, padrão 100) e `deslocamento` (padrão 0), no padrão do repo. Ordem: mais recentes primeiro, com `id` como desempate. O total que o filtro alcança vem no cabeçalho `X-Total-Count`. Para o navegador ler esse cabeçalho, ele é exposto no CORS (`expose_headers`), junto com `Retry-After`.

Quem tinha mais de 100 notificações passa a receber só as 100 mais recentes até paginar.

## Leitura

`lida_em` é preenchido uma vez. Marcar de novo uma já lida devolve a notificação com o `lida_em` original, e marcar todas repetidas devolve `marcadas = 0`. A atualização é um `UPDATE` atômico, então chamadas simultâneas não se atrapalham.

## Serviço único `notificar`

```python
from app.services.notificacao import notificar

await notificar(
    db,
    [usuario_id, ...],
    TipoNotificacao.CHAT,
    "Nova mensagem",
    "Maria escreveu na conversa",
    chave=f"chat:{mensagem_id}",
    referencia_tipo="CONVERSA",
    referencia_id=conversa_id,
    dados={"conversa_id": conversa_id},
)
```

- Chamado **dentro da transação do fato gerador**, sem commit.
- **Idempotente por `(usuario_id, chave)`**: `INSERT ... ON CONFLICT DO NOTHING` no banco, igual a `emails_outbox`. Repetir o fato, inclusive com transações simultâneas, não cria duplicata. Devolve quantos avisos novos criou.
- **Não derruba a ação principal:** a gravação roda num savepoint. Se falhar, o erro vai para o log, nada é gravado, a transação de quem chamou segue válida e o retorno é `None`. Antes do savepoint o serviço faz `flush`, para que um erro das escritas do próprio fato (por exemplo, violação de unicidade) chegue a quem chamou e não seja engolido.
- **Exceção, o resultado (RF33):** é atômico com a homologação. A linha da central é criada na mesma transação, sem savepoint, e se falhar a homologação inteira é desfeita. O tipo `RESULTADO` não é aceito por `notificar`.
- **CHAT nunca gera e-mail:** `notificar` só grava na central e não usa o módulo de e-mail. Nenhum fluxo de e-mail existe para esse tipo (decisão de 05/11, RN32). Os produtores de chat e de prazo ainda não existem; quando forem criados, basta chamar esta função.

Os produtores atuais ficam em `app/services/notificacao_eventos.py`, ao lado de `email_eventos.py`, e usam as mesmas chaves.

## Modelo de dados

Tabela `notificacoes` (migration `V202611161200__central_notificacoes.sql`): `usuario_id`, `tipo`, `titulo`, `mensagem`, `dados` (jsonb), `referencia_tipo` e `referencia_id`, `chave_idempotencia`, `notificacao_resultado_id`, `criado_em`, `lida_em`. `UNIQUE (usuario_id, chave_idempotencia)`; índices por `(usuario_id, criado_em DESC, id)` e parcial das não lidas. A constraint `ck_notificacoes_resultado` garante que só o tipo `RESULTADO` aponta para `notificacoes_resultado`.

`notificacoes_resultado` **não mudou**: segue como fonte de `status_envio`, `erro` e `pareceres` do RF33. A linha `RESULTADO` da central aponta para ela e a resposta junta as duas.

**Migração dos dados existentes.** Cada linha de `notificacoes_resultado` do canal `PLATAFORMA` e cada evento de mentoria ainda não publicado entram na central já **lidos** (`lida_em = criado_em`), para não inflar o contador de não lidas. Os eventos migrados passam a ter `publicado_na_plataforma_em` preenchido.

## Mentoria

`eventos_notificacao_mentoria` continua como registro durável de cada evento. Agora `notificacao_mentoria.registrar` também chama `notificar` (tipo `MENTOR`) e preenche `publicado_na_plataforma_em`. Se a gravação na central falhar, o evento fica com `publicado_na_plataforma_em` nulo (pendente) e a atribuição segue válida. `eventos_pendentes_plataforma()` lista esses pendentes para reprocessamento.

## Testes

`tests/test_notificacoes.py`: idempotência e concorrência (transações simultâneas), falha isolada do aviso, CHAT sem e-mail, privacidade entre usuários (inclui DEV), lidas e não lidas, contagem, paginação e `X-Total-Count`, exposição no CORS, compatibilidade do RF33, integração com cada fluxo e o backfill da migration.

---

[← Voltar ao README](../README.md)
