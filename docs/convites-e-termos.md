[← Voltar ao README](../README.md)

# Convites e termos

Rotas de RF18, RF19 e RF20. Todas exigem token e **conta ativa** (conta pendente recebe 403).

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `POST /equipes/{id}/convites` | Líder da equipe (`membros_equipe.funcao = LIDER`) | Convida por `nome` e `email`; o convite nasce `PENDENTE` |
| `GET /equipes/{id}/convites` | Integrantes da equipe | Lista os convites e o estado de cada um (o líder vê quem recusou) |
| `POST /convites/{id}/cancelar` | Líder da equipe | Retira um convite `PENDENTE` |
| `GET /convites/meus` | Qualquer usuário | Convites `PENDENTE` dirigidos ao e-mail de quem está logado (painel) |
| `POST /convites/{id}/aceitar` | Destinatário do convite | Entra na equipe e aceita os termos vigentes |
| `POST /convites/{id}/recusar` | Destinatário do convite | Recusa; a vaga volta a ficar livre |
| `GET /hackathons/{id}/termos/vigentes` | Qualquer usuário | Regulamento e termo de consentimento em vigor, para ler antes de aceitar |
| `POST /hackathons/{id}/termos/aceites` | Qualquer usuário | Registra o aceite das versões vigentes (usado, por exemplo, pelo líder ao criar a equipe) |

**Regras.**
- O convite só existe durante as inscrições (`hackathon.status = INSCRICOES`, RN06), para enviar, aceitar e recusar.
- Integrantes mais convites `PENDENTE` não passam de `hackathon.max_integrantes`. Recusar ou cancelar libera a vaga, e dá para convidar o mesmo e-mail de novo.
- Só aceita quem ainda não está em outra equipe do mesmo hackathon (RN02); a restrição única do banco garante isso mesmo com pedidos simultâneos.
- O convite é dirigido ao **e-mail**: o e-mail do convite é comparado, sem diferenciar maiúsculas, com o de quem responde. Para qualquer outra pessoa, o convite responde 404.
- Aceitar exige enviar em `termos_ids` os ids de **todas** as versões vigentes (regulamento e termo de consentimento, RN05). Faltou um: 422. Algum id que não é vigente (versão nova publicada, ou de outro hackathon): 409. A data, a hora e a versão ficam em `aceites_termos`, ligadas à linha de `termos` aceita; publicar uma versão nova não altera os aceites antigos.
- Quem entra pelo convite fica com `funcao` vazia em `membros_equipe`; o líder define as funções depois.

**Guia para a interface.** Painel do convidado: `GET /convites/meus`. Ao clicar em aceitar, buscar `GET /hackathons/{hackathon_id}/termos/vigentes` (o `hackathon_id` vem no próprio convite), mostrar `conteudo` ou `url` de cada documento e, quando a pessoa concordar, enviar os ids para `POST /convites/{id}/aceitar` com `{ "termos_ids": ["...", "..."] }`.

Ficou de fora desta etapa: envio do convite por e-mail e aviso ao líder quando alguém recusa (RF19; depende da infraestrutura de e-mail, decisão Q16). Por enquanto o líder consulta `GET /equipes/{id}/convites`.

---

[← Voltar ao README](../README.md)
