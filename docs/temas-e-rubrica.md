[← Voltar ao README](../README.md)

# Temas e rubrica — BE-S4-06 e BE-S5-08

RF15, RF16 e RF17. Quem gerencia é o perfil em `PERFIS_QUE_GERENCIAM_TEMAS_E_RUBRICAS`
(`app/security/permissoes.py`): o **Comitê Científico**, responsável pelos temas e rubricas, e
o **Organizador**, como exceção administrativa. DEV sempre passa. A configuração da edição
(datas, limites) continua só com o Organizador (`PERFIS_QUE_GERENCIAM_EDITAL`).

## Temas (RF15, RN04) e catálogo público (RF10, RF17)

| Rota | Quem acessa | Resultado |
|------|-------------|-----------|
| `POST /hackathons/{hackathon_id}/temas` | Comitê Científico, Organizador ou DEV | Cadastra; título único na edição (409 se repetido) |
| `GET /hackathons/{hackathon_id}/temas` | **Público, sem login** | Só temas ativos; `?incluir_inativos=true` exige token de quem gerencia (401 sem token, 403 para os demais) |
| `GET /temas/{tema_id}` | **Público, sem login** | Tema desativado retorna 404 para quem não gerencia, inclusive visitantes |
| `PATCH /temas/{tema_id}` | Comitê Científico, Organizador ou DEV | Edita os campos enviados; `ativo` ativa ou desativa |
| `DELETE /temas/{tema_id}` | Comitê Científico, Organizador ou DEV | 204; 409 se houver proposta ligada ao tema, inclusive rascunho |

- O tema exige `titulo`, `descricao` e pelo menos um ODS (1 a 17, sem repetição). Tema
  desativado não pode ser escolhido no rascunho nem enviado na proposta (regra já existente
  em `app/services/submissao.py`).
- Nas rotas públicas o token é opcional. Se vier, precisa ser válido (401 se não for), para o
  cliente não achar que está logado quando não está. A dependência é `usuario_opcional`
  (`app/security/dependencias.py`).
- Conta pendente não vê temas inativos, mesmo sendo do Comitê Científico.

## Rubricas: uma por fase (RF16, RF17, RN09, RN10)

Cada edição tem até **duas rubricas**, com critérios e pesos independentes:

| Fase | Usada em | Janela de publicação |
|------|----------|----------------------|
| `PROPOSTA` (padrão) | Avaliação científica das propostas (RF30) | Antes de `hackathon.inscricoes_inicio` (UTC); sem data configurada é permitida |
| `PROJETO_FINAL` | Avaliação dos projetos finais | Antes da homologação do resultado das propostas (RF31), que abre o desenvolvimento |

| Rota | Quem acessa | Resultado |
|------|-------------|-----------|
| `GET /hackathons/{hackathon_id}/rubrica?fase=` | **Público, sem login** | Rubrica publicada da fase com critérios, pesos e escalas; 404 antes da publicação |
| `GET /hackathons/{hackathon_id}/rubrica/rascunho?fase=` | Comitê Científico, Organizador ou DEV | Estado atual e `pendencias` para publicar |
| `PUT /hackathons/{hackathon_id}/rubrica?fase=` | Comitê Científico, Organizador ou DEV | Cria a rubrica da fase e substitui a lista de critérios |
| `POST /hackathons/{hackathon_id}/rubrica/publicar?fase=` | Comitê Científico, Organizador ou DEV | Publica uma única vez |

`fase` é opcional e vale `PROPOSTA` quando não é enviada, então os clientes que já usavam
estas rotas continuam funcionando sem mudança. A resposta traz o campo `fase`.

Exemplo do corpo do `PUT`:

```json
{"criterios": [
  {"nome": "Inovação", "descricao": "Originalidade", "peso": "30", "escala_min": 0, "escala_max": 10},
  {"nome": "Impacto", "descricao": "Benefício social", "peso": "30", "escala_min": 0, "escala_max": 10}
]}
```

- Cada critério tem nome (único na rubrica, sem diferenciar maiúsculas e acentos),
  descrição, peso em % (maior que 0, até 100, 2 casas) e escala com `escala_min < escala_max`.
- O rascunho pode ficar incompleto. A publicação exige ao menos um critério, **soma dos
  pesos igual a 100** e todos os critérios mínimos da fase (`CRITERIOS_MINIMOS_POR_FASE` em
  `app/const/rubrica.py`); caso contrário, 422 com o motivo.
- Fora da janela da fase, a publicação retorna 409.
- Publicada, a rubrica não muda (RN09): `PUT` e nova publicação retornam 409. A migration
  `V202611031000__rubricas.sql` também impede no banco, por trigger, alterar a rubrica
  publicada ou incluir, alterar e remover critérios dela. Excluir a rubrica inteira (com os
  critérios em cascata) continua possível, para remoção de uma edição.
- Publicar uma fase não publica nem trava a outra.
- `PUT` e publicação travam a linha do hackathon, então chamadas simultâneas são serializadas,
  inclusive com a homologação do resultado (que decide a janela do projeto final).

## Migração da rubrica existente

A migration `V202611131000__rubricas_por_fase.sql`:

- cria o tipo `fase_rubrica` e a coluna `rubricas.fase`, com padrão `PROPOSTA`. A rubrica que
  já existia em cada edição vira a da proposta. O `ADD COLUMN` com padrão não dispara os
  gatilhos de `UPDATE`, então a rubrica publicada, os critérios e as avaliações feitas com
  ela ficam exatamente como estavam;
- troca a unicidade `uq_rubricas_hackathon` por `uq_rubricas_hackathon_fase` (uma por fase);
- impede no banco que uma avaliação científica (`avaliacoes.rubrica_id`) aponte para a
  rubrica do projeto final (`avaliacao_rubrica_fase`).

**Pendências:**

- A lista oficial dos critérios mínimos da RN10 não estava documentada; os nomes em
  `CRITERIOS_MINIMOS_RN10` (Inovação, Impacto, Viabilidade técnica, Aderência ao tema) são
  provisórios. A RN10 também não separa as fases: até o time definir, o projeto final exige
  a mesma lista.
- A janela do projeto final (até a homologação do resultado das propostas) é a leitura desta
  entrega para "publicação em janela correta"; confirmar com o Squad 1.
- As regras de temas ainda dependem das validações Q02 (Fase 0 dentro ou fora do sistema) e
  Q03 (quantidade de temas e participação). Nada aqui limita a quantidade de temas.
- A avaliação do projeto final (notas pela rubrica `PROJETO_FINAL`) é de outra tarefa; esta
  entrega só cadastra e publica a rubrica.

---

[← Voltar ao README](../README.md)
