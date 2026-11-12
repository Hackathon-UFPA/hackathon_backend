[← Voltar ao README](../README.md)

# E-mails transacionais

BE-S5-05 (RNF28, RF60; RF01, RF04, RF08, RF18, RF19, RF22, RF28, RF33, RF37). Envio assíncrono e confiável de e-mails em português, por um provedor configurável, com tentativas automáticas e status de entrega rastreável.

A decisão Q16 está encerrada no documento de requisitos: as notificações do sistema (RF60) saem por **e-mail e plataforma**. A exceção é o chat entre equipe e mentor (RF43, RN32), que gera aviso só na plataforma e **nunca** por e-mail.

## Como funciona

```
ação do sistema (convite, inscrição, protocolo...)
        │  mesma transação
        ▼
 emails_outbox (fila)  ──►  worker  ──►  provedor (SMTP ou console)
   PENDENTE                 a cada 15 s    │
        ▲                                  ├─ aceitou  → ENVIADO (corpo apagado)
        └── erro temporário: espera e tenta de novo ◄──┤
                                           └─ erro permanente ou tentativas esgotadas → FALHA
```

1. **Outbox transacional.** O e-mail é gravado em `emails_outbox` na **mesma transação** da ação que o originou. Ele só existe se a ação for confirmada, e nenhum aviso se perde se a API cair logo depois.
2. **A ação principal nunca depende do provedor.** O envio acontece depois, no worker. Se o provedor estiver fora do ar, a ação já foi concluída e o e-mail espera na fila.
3. **Quem enfileira não derruba a ação.** Se o aviso não puder ser gravado (destinatário inválido, template quebrado, erro no banco), o problema vai para o log e a ação segue. A gravação roda num savepoint, então o erro não invalida a transação de quem chamou.
4. **Sem duplicar.** Cada aviso tem uma chave de idempotência (ex.: `convite:{id}`). Repetir a ação não enfileira o mesmo aviso duas vezes.

## Eventos que geram e-mail

| Evento                                        | Tipo                  | Quem recebe                              | Requisitos          |
|-----------------------------------------------|-----------------------|------------------------------------------|---------------------|
| Líder convida um integrante                   | `CONVITE_EQUIPE`      | O convidado (tenha ou não conta)         | RF18, RF19, RF60    |
| Líder conclui a inscrição da equipe           | `INSCRICAO_CONCLUIDA` | Todos os integrantes, com o protocolo    | RF22, RF60          |
| Equipe passa a homologada                     | `EQUIPE_HOMOLOGADA`   | Todos os integrantes                     | RF23, RF60          |
| Proposta enviada                              | `PROTOCOLO_PROPOSTA`  | O líder da equipe, com o protocolo       | RF28                |
| Resultado homologado                          | `RESULTADO_PROPOSTA`  | Todos os integrantes, aprovada ou não    | RF33, RF60          |
| Cadastro ou renovação de convite de mentor     | `DEFINICAO_SENHA`     | O mentor, com link temporário de uso único | RF37, RN33, BE-S5-10 |

Os templates de confirmação e recuperação abaixo ainda dependem dos respectivos fluxos de conta. `DEFINICAO_SENHA` já é usado pelo cadastro e convite de [mentores](mentores.md); seu uso para comitês segue pendente. Novos fluxos podem chamar `enfileirar` (veja mais abaixo):

| Tipo                | Uso previsto                                                    | Requisitos      | Tarefa      |
|---------------------|-----------------------------------------------------------------|-----------------|-------------|
| `CONFIRMACAO_EMAIL` | Confirmação do e-mail informado no cadastro                     | RF01            | BE-S5-07    |
| `RECUPERACAO_SENHA` | Link temporário para redefinir a senha                          | RF04            | BE-S5-07    |
| `DEFINICAO_SENHA`   | Acesso de mentores (RN33); comitês ainda sem gatilho            | RF08, RF37      | [BE-S5-10](mentores.md) |

Mensagens de chat nunca geram e-mail (RN32): não existe tipo nem gatilho para elas.

## O que vai no e-mail

Só o **aviso e o link** para a plataforma (RNF28). Nunca vão parecer, nota, senha ou documento (RNF16, RNF17). O HTML escapa todos os valores recebidos. Datas aparecem no horário de Brasília (UTC-3), como pede a RNF13. O link usa `FRONTEND_URL`.

Os templates ficam em `app/templates/emails/`: um par `<tipo>.txt` e `<tipo>.html` para cada `TipoEmail`, mais o layout `_base.html`. O assunto de cada tipo fica em `app/services/email_template.py`, junto com a lista de valores que cada template exige. Faltar um valor é erro de quem chama, nunca um e-mail pela metade.

## Estados e tentativas

Convites de mentor revogados usam `FALHA` com `cancelado_em` preenchido. Essas mensagens têm seus corpos eliminados e não podem ser reenviadas por `/admin/emails`: o gestor emite outro convite com a edição explícita. A reserva já confirmada é revalidada pelo worker antes da entrega. Mensagens já enviadas permanecem intactas. Detalhes e limites de concorrência em [Mentores](mentores.md).

| Status      | Significado                                                                                  |
|-------------|----------------------------------------------------------------------------------------------|
| `PENDENTE`  | Na fila: ainda não tentou, ou espera a hora da próxima tentativa (`proxima_tentativa_em`)    |
| `ENVIANDO`  | Reservado por um worker (`reservado_ate`)                                                    |
| `ENVIADO`   | O provedor aceitou. O corpo é apagado, pois pode ter links de acesso                         |
| `FALHA`     | Erro permanente ou tentativas esgotadas. Só volta para a fila com o reenvio manual           |

**Erro temporário** (servidor fora do ar, tempo esgotado, limite do provedor, credencial recusada): o e-mail volta a `PENDENTE` com espera crescente, `base * 2^(tentativa-1)`, limitada ao teto. Com os valores padrão: 30 s, 1 min, 2 min, 4 min e, na quinta falha, `FALHA`. O primeiro envio sai em até 15 s (intervalo do worker), dentro da meta de 5 minutos da RNF28.

**Erro permanente** (destinatário ou remetente recusado, mensagem rejeitada): vai direto para `FALHA`, sem gastar as demais tentativas.

**Worker que cai no meio do envio:** a reserva vence (`EMAIL_RESERVA_SEGUNDOS`) e o e-mail volta para a fila. A garantia é "pelo menos uma vez": se a queda acontecer depois de o provedor aceitar a mensagem e antes de registrar, ela pode sair de novo.

**Vários workers ou instâncias:** a reserva usa `FOR UPDATE SKIP LOCKED`, então nunca pegam o mesmo e-mail.

## Rotas de acompanhamento

Restritas a Organizador (e DEV). Nenhuma resposta traz o conteúdo da mensagem.

| Rota                                | O que faz                                                                         |
|-------------------------------------|-----------------------------------------------------------------------------------|
| `GET /admin/emails`                 | Lista os e-mails, do mais recente ao mais antigo. Filtros `status`, `tipo`, `destinatario`; paginação `limite` (1 a 100, padrão 50) e `deslocamento` |
| `GET /admin/emails/{id}`            | Situação de um e-mail: tentativas, próxima tentativa, último erro e data do envio |
| `POST /admin/emails/{id}/reenviar`  | Devolve à fila um e-mail em `FALHA`, com as tentativas zeradas                     |

Erros: 401 (sem token ou token inválido), 403 (perfil sem permissão ou conta pendente), 404 (e-mail inexistente), 409 no reenvio (o e-mail não está em `FALHA`: reenviar um `PENDENTE`, `ENVIANDO` ou `ENVIADO` duplicaria o aviso) e 422 (parâmetro inválido). Dois reenvios simultâneos resultam em um 200 e um 409. O detalhe de cada rota está no Swagger, na tag **E-mails**.

## Configuração

Tudo vem de variáveis de ambiente (veja o `.env.example`). **Credenciais ficam só no ambiente**, nunca no código nem no repositório.

| Variável                       | Padrão                          | Descrição                                                                    |
|--------------------------------|---------------------------------|------------------------------------------------------------------------------|
| `EMAIL_PROVIDER`               | `console`                       | `console` só registra no log (nada é enviado). `smtp` envia de verdade       |
| `EMAIL_REMETENTE_NOME`         | `Hackathon UFPA`                | Nome do remetente único do hackathon                                         |
| `EMAIL_REMETENTE_ENDERECO`     | `nao-responder@hackathon.local` | Endereço do remetente                                                        |
| `SMTP_HOST`, `SMTP_PORT`       | vazio, `587`                    | Servidor SMTP. Com `EMAIL_PROVIDER=smtp`, o host é obrigatório: a API não sobe sem ele |
| `SMTP_USUARIO`, `SMTP_SENHA`   | vazio                           | Credenciais. A senha nunca aparece em log, erro ou resposta da API           |
| `SMTP_SEGURANCA`               | `starttls`                      | `starttls` (porta 587), `ssl` (porta 465) ou `nenhuma` (só servidor local)   |
| `SMTP_TIMEOUT_SEGUNDOS`        | `30`                            | Tempo máximo de cada conexão                                                 |
| `FRONTEND_URL`                 | `http://localhost:4200`         | Endereço do front, usado nos links                                           |
| `EMAIL_WORKER_ATIVO`           | `true`                          | Liga o worker dentro da API. Os testes o desligam                            |
| `EMAIL_INTERVALO_SEGUNDOS`     | `15`                            | Intervalo entre as rodadas do worker                                         |
| `EMAIL_LOTE`                   | `20`                            | E-mails por rodada                                                           |
| `EMAIL_MAX_TENTATIVAS`         | `5`                             | Tentativas por e-mail antes de `FALHA`                                       |
| `EMAIL_BACKOFF_BASE_SEGUNDOS`  | `30`                            | Espera depois da primeira falha; dobra a cada tentativa                      |
| `EMAIL_BACKOFF_MAX_SEGUNDOS`   | `1800`                          | Teto da espera                                                               |
| `EMAIL_RESERVA_SEGUNDOS`       | `300`                           | Depois deste prazo, um envio reservado e não concluído volta para a fila     |

Para testar com um servidor SMTP local, suba um coletor como o MailHog e use `SMTP_HOST=localhost`, `SMTP_PORT=1025`, `SMTP_SEGURANCA=nenhuma`.

## Segurança e privacidade

1. O corpo do e-mail é apagado assim que o provedor aceita a mensagem. Enquanto está na fila, o conteúdo só existe no banco, e a API administrativa nunca o devolve.
2. O banco recusa destinatário ou assunto com caracteres de controle (`ck_emails_outbox_destinatario` e `ck_emails_outbox_assunto`), e o provedor SMTP recusa quebra de linha em qualquer cabeçalho. Isso impede injeção de cabeçalhos (por exemplo, `Bcc:` escondido no nome).
3. Mensagens de erro guardadas em `ultimo_erro` trazem a classe do erro e a resposta do servidor, limitadas a 500 caracteres, e nunca credenciais.
4. Todo e-mail sai com o cabeçalho `Auto-Submitted: auto-generated` e o aviso de que não deve ser respondido.
5. **Opt-out:** os tipos desta entrega são e-mails de conta e de processo (acesso, protocolo, resultado), que a pessoa precisa receber para participar. Eles não têm opt-out. O descadastro só se aplica a mensagens opcionais, como lembretes (RF61) e comunicados (RF62), que ainda não existem.

## Usando em um fluxo novo

Dentro do service, na mesma transação da ação, antes do `commit`:

```python
from app.const.enums import TipoEmail
from app.services.email import enfileirar, link_front

await enfileirar(
    db,
    TipoEmail.RECUPERACAO_SENHA,
    destinatario_email=usuario.email,
    destinatario_nome=usuario.nome,
    usuario_id=usuario.id,
    contexto={
        "nome": usuario.nome or "participante",
        "link": link_front(f"/redefinir-senha?token={token}"),
        "validade_minutos": 30,
    },
    chave=f"recuperacao:{pedido.id}",  # evita avisar duas vezes pelo mesmo fato
)
await db.commit()
```

Para um tipo novo: acrescente o valor em `TipoEmail` (enum em `app/const/enums.py` **e** `ALTER TYPE tipo_email ADD VALUE` em uma migration nova), o assunto e os valores obrigatórios em `app/services/email_template.py` e o par `.txt` e `.html` em `app/templates/emails/`.

Os avisos dos eventos existentes ficam em `app/services/email_eventos.py`. O envio em si (`processar_lote`) está em `app/services/email_envio.py` e o worker em `app/jobs/email.py`, iniciado no lifespan da API.

## Testes

Nenhum teste envia e-mail de verdade: usam o provedor falso `ProvedorMemoria` (em `app/integrations/email.py`), que guarda as mensagens e falha sob comando, e um servidor SMTP simulado para o `ProvedorSmtp`. O worker fica desligado nos testes (`tests/__init__.py`), e cada teste roda os lotes que precisa. Cobertura:

1. `tests/test_email_templates.py`: todos os tipos, escape de HTML, assunto em uma linha, horário de Brasília, nada de parecer ou nota.
2. `tests/test_email_provedores.py`: montagem da mensagem, STARTTLS e SSL, classificação de erros temporários e permanentes, senha fora de erros e configuração, validação das variáveis.
3. `tests/test_email_fila.py`: gravação, idempotência, atomicidade com a transação, isolamento de falhas, restrições do banco.
4. `tests/test_email_envio.py`: sucesso, tentativas e espera crescente, fim das tentativas, reservas vencidas e workers simultâneos.
5. `tests/test_email_api.py`: permissões, filtros, paginação, reenvio (inclusive simultâneo) e Swagger.
6. `tests/test_email_eventos.py`: quem é avisado em cada evento real e que nada é enviado quando a ação é recusada ou desfeita.

---

[← Voltar ao README](../README.md)
