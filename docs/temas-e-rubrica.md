[← Voltar ao README](../README.md)

# Temas e rubrica — BE-S4-06

RF15, RF16 e RF17. Quem gerencia é o perfil em `PERFIS_QUE_GERENCIAM_EDITAL`
(`app/security/permissoes.py`, hoje só `ORGANIZADOR`); DEV sempre passa.

## Temas (RF15, RN04)

| Rota | Quem acessa | Resultado |
|------|-------------|-----------|
| `POST /hackathons/{hackathon_id}/temas` | Organizador ou DEV | Cadastra; título único na edição (409 se repetido) |
| `GET /hackathons/{hackathon_id}/temas` | Conta ativa | Só temas ativos; `?incluir_inativos=true` apenas para Organizador/DEV (403 para os demais) |
| `GET /temas/{tema_id}` | Conta ativa | Tema desativado retorna 404 para quem não gerencia |
| `PATCH /temas/{tema_id}` | Organizador ou DEV | Edita os campos enviados; `ativo` ativa ou desativa |
| `DELETE /temas/{tema_id}` | Organizador ou DEV | 204; 409 se houver proposta ligada ao tema, inclusive rascunho |

O tema exige `titulo`, `descricao` e pelo menos um ODS (1 a 17, sem repetição). Tema
desativado não pode ser escolhido no rascunho nem enviado na proposta (regra já existente
em `app/services/submissao.py`).

## Rubrica (RF16, RF17, RN09, RN10)

| Rota | Quem acessa | Resultado |
|------|-------------|-----------|
| `GET /hackathons/{hackathon_id}/rubrica` | **Público, sem login** | Rubrica publicada com critérios, pesos e escalas; 404 antes da publicação |
| `GET /hackathons/{hackathon_id}/rubrica/rascunho` | Organizador ou DEV | Estado atual e `pendencias` para publicar |
| `PUT /hackathons/{hackathon_id}/rubrica` | Organizador ou DEV | Cria a rubrica da edição e substitui a lista de critérios |
| `POST /hackathons/{hackathon_id}/rubrica/publicar` | Organizador ou DEV | Publica uma única vez |

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
  pesos igual a 100** e todos os critérios de `CRITERIOS_MINIMOS_RN10` (`app/const/rubrica.py`);
  caso contrário, 422 com o motivo.
- A publicação precisa ocorrer **antes de `hackathon.inscricoes_inicio`** (UTC); depois, 409.
  Sem data configurada, é permitida.
- Publicada, a rubrica não muda (RN09): `PUT` e nova publicação retornam 409. A migration
  `V202611031000__rubricas.sql` também impede no banco, por trigger, alterar a rubrica
  publicada ou incluir, alterar e remover critérios dela. Excluir a rubrica inteira (com os
  critérios em cascata) continua possível, para remoção de uma edição.
- `PUT` e publicação travam a linha do hackathon, então chamadas simultâneas são serializadas.

**Pendências:** a lista oficial dos critérios mínimos da RN10 não estava documentada; os
nomes em `CRITERIOS_MINIMOS_RN10` (Inovação, Impacto, Viabilidade técnica, Aderência ao tema)
são provisórios. As regras de temas ainda dependem das validações Q02 (Fase 0 dentro ou fora
do sistema) e Q03 (quantidade de temas e participação).

---

[← Voltar ao README](../README.md)
