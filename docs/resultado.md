[← Voltar ao README](../README.md)

# Homologação do resultado e propostas aprovadas — BE-S4-11

RF31 e RF32.

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `GET /admin/hackathons/{id}/resultado` | Organizador (e DEV) | Notas consolidadas, classificação, pendências e `pode_homologar`; depois da homologação, o resultado oficial |
| `POST /admin/hackathons/{id}/resultado/homologar` | Organizador (e DEV) | Homologa o resultado com a lista `propostas_aprovadas` |
| `GET /hackathons/{id}/propostas-aprovadas` | Público, sem login | Equipe, tema e título das propostas aprovadas, só depois da homologação |

## Consolidação (RF31)

Entram as propostas `ENVIADA` do hackathon. Para cada uma, contam só as avaliações dos avaliadores **designados** a ela e com `status = ENVIADA`; rascunhos não entram na média.

- **Nota média:** média simples das notas finais (`avaliacoes.nota`), com `Decimal` e arredondamento `ROUND_HALF_UP` em duas casas só no fim. Ex.: 8 e 7,35 → 7,68.
- **Classificação:** maior média primeiro. Empate: mais recomendações `APROVACAO`, depois quem enviou a proposta antes (`enviado_em`), depois o id. Proposta sem nenhuma avaliação enviada fica com `classificacao = null`.
- **Recomendações:** contagem de `APROVACAO` e `REPROVACAO`.

## Quando é possível homologar

`pendencias` lista o que impede, e `pode_homologar` só é verdadeiro sem nenhuma:

| Código | Quando |
|--------|--------|
| `QUANTIDADE_NAO_CONFIGURADA` | `hackathon.avaliadores_por_proposta` ainda é `NULL` |
| `SEM_PROPOSTAS` | Nenhuma proposta `ENVIADA` |
| `AVALIADORES_INSUFICIENTES` | Proposta com menos avaliadores designados que o configurado |
| `AVALIACAO_PENDENTE` | Algum avaliador designado ainda não enviou a avaliação (inclusive quem só tem rascunho) |

Com pendências, `POST .../homologar` responde 409 e não grava nada.

## Homologação

O corpo traz a decisão do Organizador:

```json
{"propostas_aprovadas": ["3fa85f64-5717-4562-b3fc-2c963f66afa6"]}
```

As propostas listadas ficam aprovadas e as demais reprovadas (lista vazia reprova todas). Repetidos ou ids que não são propostas `ENVIADA` do hackathon respondem 422.

**Decisão em aberto:** os critérios definitivos de aprovação (nota de corte, número de vagas, peso das recomendações) ainda não foram definidos. Por isso a API não aprova sozinha: a consulta mostra média, classificação e recomendações, e quem decide é o Organizador. Quando o critério for definido, ele pode virar uma sugestão na consulta ou uma validação na homologação.

**Auditoria.** `homologacoes_resultado` guarda `homologado_por`, `homologado_em` (UTC) e os totais, e é única por hackathon. `resultados_proposta` guarda um retrato de cada proposta: nome da equipe, tema, título, média, classificação, número de avaliações, recomendações e se foi aprovada. A consulta administrativa e a pública leem esse retrato, então renomear a equipe depois não muda o resultado divulgado.

**Bloqueio.** Depois de homologado:

- homologar de novo responde 409;
- salvar ou enviar avaliação (`/avaliador/propostas/{id}/avaliacao/*`) responde 409;
- distribuir, redistribuir e configurar `avaliadores_por_proposta` respondem 409;
- triggers no banco impedem `UPDATE` em `homologacoes_resultado` e `resultados_proposta` (`resultado_homologado_imutavel`). Excluir continua possível, para remover uma edição inteira.

Não existe rota para desfazer a homologação.

**Concorrência.** A homologação trava a linha do `hackathon` (`SELECT ... FOR UPDATE`), o mesmo lock usado pela distribuição e pelo registro de avaliações. Uma avaliação enviada ao mesmo tempo ou entra antes da homologação ou recebe 409.

## Divulgação (RF32)

`GET /hackathons/{id}/propostas-aprovadas` não exige token. Antes da homologação responde 200 com `divulgado = false` e lista vazia: nenhum dado de avaliação aparece. Depois, lista só as aprovadas, com `equipe`, `tema` e `titulo`, em ordem alfabética pela equipe, sem notas nem classificação. Hackathon inexistente responde 404.

---

[← Voltar ao README](../README.md)
