[← Voltar ao README](../README.md)

# Notificação do resultado e somente leitura — BE-S4-12

RF33 e RF34. Dependem de RF31, RF32 ([Resultado](resultado.md)) e RF06.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `POST /admin/hackathons/{id}/resultado/homologar` | Organizador (e DEV) | Além de homologar, cria as notificações dos integrantes na mesma transação |
| `GET /me/notificacoes` | Qualquer usuário autenticado e ativo | Lista as notificações do próprio usuário, da mais recente para a mais antiga |
| `GET /equipes/{id}/resultado` | Integrantes da equipe e DEV | Resultado e pareceres da própria equipe |

## Notificação (RF33)

**Canal.** A decisão Q16 foi encerrada: o resultado é avisado por **plataforma e e-mail**. Na plataforma, a notificação fica disponível em `GET /me/notificacoes` (canal `PLATAFORMA`). Por e-mail, o aviso `RESULTADO_PROPOSTA` entra na fila de e-mails na mesma transação da homologação (veja [E-mails](emails.md)) e diz apenas se a proposta foi aprovada, com o link para a plataforma, sem parecer nem nota. O status de entrega do e-mail é acompanhado em `GET /admin/emails`, e não em `notificacoes_resultado`: o valor `EMAIL` do enum `canal_notificacao` continua reservado e sem uso.

**Destinatários.** Todos os integrantes (`membros_equipe`) de cada equipe com proposta no resultado, aprovada ou não. Equipes sem proposta enviada não entram no resultado e não são notificadas.

**Conteúdo.** `aprovada`, uma `mensagem` dizendo se a proposta foi aprovada ou não, e `pareceres` (texto e recomendação, sem identificar o avaliador).

**Status de envio rastreável.** Tabela `notificacoes_resultado`:

| Campo | Significado |
|-------|-------------|
| `canal` | `PLATAFORMA` (único em uso) ou `EMAIL` (reservado) |
| `status_envio` | `PENDENTE`, `ENVIADO` ou `FALHA` |
| `enviado_em` | Obrigatório quando `ENVIADO` |
| `erro` | Só aceito quando `FALHA` |

Na plataforma a linha nasce `ENVIADO`, porque o aviso já está visível ao integrante. Há uma notificação por `(homologação, usuário, canal)`. Não existe "marcar como lida".

**Atomicidade.** As notificações são criadas na transação da homologação. Se não for possível criá-las, a homologação inteira falha (rollback): como ela é imutável, não pode existir sem o aviso.

## Resultado da própria equipe

`GET /equipes/{id}/resultado`:

- 401 sem token; 403 se não for integrante (nem DEV); 404 se a equipe não existe.
- Antes da homologação: 200 com `divulgado = false`, sem dados de avaliação.
- Depois: `aprovada`, `somente_leitura`, título e `pareceres` (`parecer` e `recomendacao`). **Não traz nota média nem classificação.**
- Equipe sem proposta com resultado homologado: 404.

Mostrar os pareceres à equipe muda a regra de [Avaliação](avaliacao.md) e **depende de confirmação do grupo**.

## Somente leitura (RF34)

**Equipe não aprovada:** depois da homologação, a equipe cuja proposta tem `resultados_proposta.aprovada = false`. Sem homologação nada muda; equipes aprovadas não são afetadas.

**Equipe sem proposta enviada fica editável.** Ela não aparece em `resultados_proposta`, então não foi reprovada. Esta é uma regra **a confirmar com o grupo**.

O bloqueio é no servidor (`app/services/somente_leitura.py`, função `exigir_equipe_editavel`) e responde **409** com a mensagem "A proposta desta equipe não foi aprovada no resultado do hackathon. A equipe está em modo somente leitura...". Vale também para DEV. A checagem vem logo após a autorização (líder ou destinatário) e antes das demais validações.

Rotas cobertas:

| Rota | Quem |
|------|------|
| `PATCH /equipes/{id}` | Líder |
| `PATCH` e `DELETE /equipes/{id}/membros/{usuario_id}` | Líder |
| `POST /equipes/{id}/convites` | Líder |
| `POST /convites/{id}/cancelar` | Líder |
| `POST /convites/{id}/aceitar` e `/recusar` | Convidado (vale pela equipe do convite) |
| `POST /equipes/{id}/inscricao/concluir` | Líder |
| `POST /equipes/{id}/proposta/rascunho`, `PATCH .../rascunho`, `POST .../proposta/enviar` | Líder |

Continuam permitidas as consultas: equipe, membros, convites, painel, proposta, rascunho, resultado da equipe e notificações.

Fora do bloqueio, por não serem de uma equipe: `POST /equipes` (nova equipe), `POST /hackathons/{id}/termos/aceites` (aceite do usuário, sem equipe), comprovantes e as rotas de Organizador, avaliador e rubrica.

**Corrida aceita.** Uma escrita que passou na checagem antes do commit da homologação vale: a homologação não espera escritas em andamento da equipe.

---

[← Voltar ao README](../README.md)
