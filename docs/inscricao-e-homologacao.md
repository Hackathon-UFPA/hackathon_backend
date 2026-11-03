# Inscrição e homologação

BE-S4-05 (RF21, RF22, RF23, RF25).

| Rota                                              | Quem acessa                                       | O que faz                                                                                                  |
|---------------------------------------------------|---------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| `GET /admin/comprovantes`                         | Organizador e Comitê Científico (e DEV)           | Fila de comprovantes (padrão `PENDENTE`, filtros `status`, `hackathon_id`, `limite`, `deslocamento`), com `arquivo_url` e dados de quem enviou |
| `POST /admin/comprovantes/{id}/aprovar`           | Organizador e Comitê Científico (e DEV)           | Aprova o vínculo, ativa a conta e reavalia a homologação da equipe                                         |
| `POST /admin/comprovantes/{id}/recusar`           | Organizador e Comitê Científico (e DEV)           | Recusa com `motivo_recusa` obrigatório                                                                     |
| `GET /comprovantes/meus`                          | Qualquer usuário logado, inclusive conta pendente | Histórico dos próprios comprovantes, com o motivo da recusa                                                |
| `POST /comprovantes`                              | Qualquer usuário logado, inclusive conta pendente | Reenvia o comprovante (`arquivo_url`) depois de uma recusa; o anterior fica no histórico                   |
| `GET /equipes/{id}/painel`                        | Integrantes da equipe (e DEV)                     | Situação da equipe, estado de cada integrante (convite, termos, comprovante) e lista do que falta          |
| `POST /equipes/{id}/inscricao/concluir`           | Líder da equipe (e DEV)                           | Conclui a inscrição, emite o protocolo e devolve a confirmação                                             |
| `POST /admin/hackathons/{id}/equipes/reavaliar`   | Organizador (e DEV)                               | Refaz a homologação das equipes com inscrição concluída                                                    |

**Ciclo da equipe.** `EM_FORMACAO` → (líder conclui) `AGUARDANDO_HOMOLOGACAO` → (requisitos cumpridos) `HOMOLOGADA`. A homologação volta para `AGUARDANDO_HOMOLOGACAO` sozinha quando um requisito deixa de valer. `NAO_HOMOLOGADA` fica reservada ao encerramento do prazo de homologação (`hackathon.homologacao_fim`), que ainda não tem job.

**Concluir a inscrição** exige, ao mesmo tempo: líder logado, equipe em `EM_FORMACAO`, inscrições abertas (`status = INSCRICOES` e, se o edital define `inscricoes_inicio`/`inscricoes_fim`, o momento atual dentro delas), de `min_integrantes` a `max_integrantes` (3 a 5 por padrão, Q04 em aberto), e cada integrante com convite aceito, conta ativa e as versões vigentes do regulamento e do termo de consentimento aceitas, o líder inclusive. O comprovante **não** é exigido para concluir. Ao concluir, convites sem resposta são cancelados, a composição da equipe fecha (novos convites e aceites dão 409) e um protocolo `INSCRICAO_EQUIPE` é emitido (um por equipe, garantido por índice único). Se o vínculo de todos já estiver aprovado, a equipe sai homologada na mesma chamada.

**Homologação automática** (RF23): além do que vale para concluir, todos os integrantes precisam ter o comprovante mais recente `APROVADO` no hackathon. A reavaliação roda ao concluir, ao aprovar um comprovante e em `POST /admin/hackathons/{id}/equipes/reavaliar`. Quem publicar uma nova versão de termos (ou mudar o tamanho de equipe) deve chamar `reavaliar_hackathon` do `app/services/inscricao.py` ou essa rota, para equipes homologadas que deixaram de cumprir os requisitos voltarem a pendentes. A lógica única fica em `app/services/homologacao.py`: o painel, a conclusão e a homologação usam a mesma avaliação.

**Painel.** `pendencias` lista cada coisa que falta, com `codigo`, `mensagem`, a pessoa responsável (`usuario_id`) e `bloqueia_conclusao`. `pode_concluir` é a flag para a interface mostrar o botão de concluir: só é verdadeira para o líder, com a equipe em formação e nenhum bloqueio. Convites sem resposta ou recusados aparecem na lista de `integrantes` com `integrante = false`.

**Decisões em aberto que o código assume** (ajuste se a equipe decidir diferente):

- **Q25, quem confere o comprovante.** A história de usuário diz Organizador e o comentário do banco diz Comitê Científico; as rotas aceitam os dois. A lista fica em `PERFIS_QUE_VALIDAM_COMPROVANTE`, em `app/security/permissoes.py`.
- **Quem não tem comprovante.** "Vínculo validado" significa ter comprovante `APROVADO` no hackathon. Participante cadastrado por um gestor (conta ativa, sem comprovante) segura a homologação até enviar um com `POST /comprovantes` e ser aprovado.
- **Recusa.** Só comprovantes `PENDENTE` são decididos; um comprovante aprovado não é revogado por esta API.
- **Avisos.** A documentação já registra que não há infraestrutura de e-mail ou notificações. "O integrante é avisado" (RF21) e "a equipe é avisada" (RF23) ficam atendidos pela consulta: `GET /comprovantes/meus` e `GET /equipes/{id}/painel`.
- **Prazo.** A conclusão confere também as datas do edital quando existem, ao contrário das demais rotas, que olham só o `status`.
