[← Voltar ao README](../README.md)

# Conteúdo institucional e treinamento

BE-S5-12 (RF10 a RF14, RF35, RF59; RN05, RN07, RN09; RNF20, RNF23). Páginas e rotas para divulgar a edição: descrição, regulamento com versões, FAQ ordenável, cronograma, apoiadores e agenda do treinamento.

**Regras gerais**

- **Gestão** só pelo **Organizador** (e DEV), conforme `PERFIS_QUE_GERENCIAM_EDITAL`. O Comitê Científico e os demais perfis recebem 403, sem token 401.
- **Publicação.** Todo conteúdo nasce **não publicado** (`publicado = false`; o regulamento nasce rascunho). O público só vê o que foi publicado. Uma edição em `RASCUNHO` não aparece em nenhuma rota pública (404).
- **Só links, nunca arquivos (RNF20).** A API não recebe nem guarda arquivos: logo, PDF do regulamento e materiais ficam em um serviço externo (Cloudinary, Drive...) e a API guarda o link. Política proposta, **a validar com o grupo (Q14)**: `https`, até 2048 caracteres, sem espaços internos nem caracteres de controle e sem usuário e senha no endereço; espaços e quebras de linha nas pontas são aparados. O **logo** precisa terminar em `.png`, `.jpg`, `.jpeg`, `.webp` ou `.svg`. Enviar um arquivo (multipart) dá 422. O código fica em `app/validations/links.py`.
- **Itens pertencem a uma edição.** O id de um item de outra edição responde 404.
- **Datas em UTC.** Data sem fuso vale como UTC; com fuso é convertida (RNF13). `fim` nunca é antes de `inicio` (422), inclusive no `PATCH`, onde o período final é validado com os valores já gravados.
- **Campo desconhecido ou `null` em campo obrigatório no `PATCH` dá 422.**
- **Listas** da administração aceitam `limite` (1 a 100, padrão 50) e `deslocamento`, e filtros onde faz sentido.

## Página pública (RF10 a RF14), sem login

| Rota | O que devolve |
|------|---------------|
| `GET /publico/hackathons` | Edições divulgadas (todas menos `RASCUNHO`), das mais recentes às mais antigas |
| `GET /publico/hackathons/{id}` | Página completa: nome, tema, **descrição**, datas, `inscricoes_abertas`, regulamento vigente, FAQ, cronograma e apoiadores |
| `GET /publico/hackathons/{id}/regulamento` | Só a versão publicada, com `publicado_em` (data da última atualização). 404 se não há |
| `GET /publico/hackathons/{id}/faq` | Perguntas publicadas, na ordem da organização |
| `GET /publico/hackathons/{id}/cronograma` | Datas do edital e fases publicadas, em ordem cronológica, com a fase atual destacada |
| `GET /publico/hackathons/{id}/apoiadores` | Apoiadores publicados, agrupados por categoria |

`inscricoes_abertas` segue a RN06 (status `INSCRICOES` dentro das datas). A interface mostra o botão de inscrição só quando for `true` e leva a pessoa à tela de cadastro (`POST /auth/cadastro`).

**Compatibilidade com o CRUD de hackathon.** `descricao` é um campo novo e opcional em `POST/PATCH /admin/hackathons`, e aparece nas respostas. Nada mudou para quem não o envia. `GET /hackathons` continua exigindo conta ativa; as rotas `/publico/...` são as abertas.

## Apoiadores (RF14)

Base: `/admin/hackathons/{id}/apoiadores`. `POST` cadastra (`nome`, `categoria`, `logo_url`, `site_url`, `publicado`), `GET` lista (filtros `publicado` e `categoria`), `PATCH /{apoiador_id}` edita (`logo_url` e `site_url` aceitam `null`; `ordem` muda a posição) e `DELETE /{apoiador_id}` exclui. Quem entra vai para o fim da lista. Na página pública os grupos seguem a posição do primeiro apoiador de cada categoria. O logo abre o `site_url`.

## FAQ ordenável (RF12)

Base: `/admin/hackathons/{id}/faq`. `POST`, `GET` (filtro `publicado`), `PATCH /{item_id}`, `DELETE /{item_id}` e **`PUT /faq/ordem`** com `{"ids": [...]}`.

- O `PUT` exige **todos** os ids da edição, na nova ordem e sem repetir. Se a lista não for exatamente o conjunto atual (alguém criou ou excluiu uma pergunta no meio do caminho), responde **409** e a interface recarrega; ids repetidos ou lista vazia dão 422.
- **Concorrência.** Criar e reordenar travam a linha da edição (`FOR UPDATE`), então criações simultâneas recebem posições distintas e reordenações simultâneas se enfileiram (a última vale, nunca uma mistura).

## Cronograma e fases do edital (RF13, RF59)

- `GET /admin/hackathons/{id}/cronograma` mostra tudo em ordem cronológica: as **datas do próprio edital** (`origem = EDITAL`, sem `id`) e as **fases cadastradas** (`origem = PERSONALIZADA`), publicadas ou não. As do edital são lidas de `hackathon` (inscrições, homologação, envio de propostas e evento), então mudar as datas em `PATCH /admin/hackathons/{id}` muda o cronograma, sem cadastro duplicado.
- Cada linha traz `situacao` (`NAO_INICIADA`, `EM_ANDAMENTO`, `ENCERRADA`) e `atual` (verdadeiro na fase em andamento, para destacar). Isso atende à **consulta** da situação de cada fase (RF59).
- `POST /cronograma`, `PATCH /cronograma/{fase_id}` e `DELETE /cronograma/{fase_id}` gerenciam as fases extras (`nome`, `descricao`, `inicio`, `fim`, `publicado`).
- **Fora do escopo:** abrir, encerrar e reabrir fases do edital, o bloqueio de operações incompatíveis com a fase vigente e o registro de responsável e data de cada mudança são da **BE-S7-05**.

## Regulamento com versões (RF11, RN05)

Reaproveita a tabela `termos` (regulamento e termo de consentimento, `tipo`), com um ciclo de vida novo. Base: `/admin/hackathons/{id}/termos`.

```
rascunho ──publicar──► vigente ──nova versão publicada──► antiga (histórico)
 (edita, exclui)        (imutável)                          (imutável, nunca volta)
```

| Rota | O que faz |
|------|-----------|
| `POST /termos` | Cria uma versão em **rascunho** (`tipo` padrão `REGULAMENTO`, `versao`, `titulo`, `conteudo` e/ou `url`). O número da versão é único por tipo na edição (409) |
| `GET /termos` | Todas as versões, por tipo e da mais recente à mais antiga. Filtros `tipo` e `rascunho` |
| `PATCH /termos/{id}` | Edita um rascunho (`titulo`, `conteudo`, `url`). Versão publicada: 409 |
| `DELETE /termos/{id}` | Exclui um rascunho. Versão publicada: 409 (ela tem aceites) |
| `POST /termos/{id}/publicar` | Torna a versão vigente e aposenta a anterior do mesmo tipo, na mesma transação |

- O texto do regulamento pode vir em `conteudo`, em `url` (link do PDF) ou nos dois; um dos dois é obrigatório.
- Uma versão **publicada não muda mais**: corrigir é publicar uma nova. Quem aceitou a antiga mantém o aceite ligado a ela (RF20), e a nova versão passa a exigir novo aceite (`GET /hackathons/{id}/termos/vigentes` já devolve a vigente).
- Publicar a versão já vigente não muda nada. Uma versão já substituída dá 409: crie outra.
- **Concorrência.** A publicação trava a edição: publicações simultâneas se enfileiram e **nunca há duas vigentes** (também garantido pelo índice único `uq_termos_vigente`).
- Termos criados antes desta entrega são tratados como publicados.

## Treinamento (RF35)

Administração em `/admin/hackathons/{id}/treinamento/...` (só Organizador/DEV):

| Rota | O que faz |
|------|-----------|
| `POST /sessoes` | Cadastra a sessão: `titulo`, `inicio`, `fim` opcional e **local ou link** (`local`, `link_url`; um dos dois é obrigatório) |
| `GET /sessoes` | Lista com os materiais, em ordem cronológica. Filtro `publicado` |
| `PATCH /sessoes/{sessao_id}` | Edita; `descricao`, `fim`, `local` e `link_url` aceitam `null`, mas a sessão precisa manter local ou link |
| `DELETE /sessoes/{sessao_id}` | Exclui a sessão e seus materiais |
| `POST /sessoes/{sessao_id}/materiais` | Anexa um material (`titulo`, `url` https), no fim da lista |
| `DELETE /sessoes/{sessao_id}/materiais/{material_id}` | Remove o material |

**Quem vê.** `GET /hackathons/{id}/treinamento` (conta ativa) devolve só as sessões **publicadas**, com os materiais. Veem: integrantes de **equipe aprovada na edição** (equipe com resultado `aprovada = true`, o mesmo critério da mentoria), o Organizador, o Comitê Científico e o DEV. Qualquer outra pessoa (equipe não aprovada, aprovada em outra edição, mentor, comitê técnico, conta pendente) recebe **403**, sem conteúdo. As rotas `GET /admin/hackathons/{id}/treinamento` e `POST .../treinamento/concluir` continuam sendo as do marco de conclusão da [mentoria](atribuicao-mentores.md).

### Decisões e pendências

- **RF36 (registrar participação no treinamento) continua removido.** Não há presença por integrante nem relatório. A recomendação é manter assim, porque depende da Q09 (onde será o treinamento); fica para **validação formal do grupo**.
- **Aviso às equipes quando algo muda (RF35, Q09) não foi implementado.** Exigiria um tipo de e-mail novo e a decisão da Q09; as sessões e os materiais já guardam `atualizado_em`, que serve de base para o gatilho.
- **Política de links (Q14, RNF20)** é proposta e está centralizada em `app/validations/links.py`: ajustar lá muda todas as rotas.

## Tabelas

`hackathon.descricao`, `termos.rascunho` e as novas `apoiadores`, `faq_itens`, `fases_cronograma`, `sessoes_treinamento` e `materiais_treinamento` (migration `V202611161100__conteudo_institucional.sql`). Veja [Banco de dados](banco-de-dados.md). Uma edição com conteúdo ligado a ela não pode ser excluída (409): cancele-a.

## Testes

`tests/test_conteudo_institucional.py`: permissões 401/403 em todas as rotas administrativas (Organizador e DEV passam; demais perfis e conta pendente, não), visibilidade pública e rascunho, política de links, validação de períodos (inclusive no `PATCH` e com fuso), ordem e destaque do cronograma, ciclo do regulamento (rascunho, publicação, substituição, imutabilidade, aceites preservados), acesso ao treinamento por equipe aprovada e concorrência (criações e reordenações do FAQ, publicações simultâneas, materiais simultâneos).

---

[← Voltar ao README](../README.md)
