[← Voltar ao README](../README.md)

# Autodeclaração e comprovantes individuais por tipo — BE-S5-03

RF01, RF18, RF20 a RF23; RN01, RN05, RN25. Depende da [BE-S5-01](equipes-e-membros.md#categorias-e-composição-informada-pelo-líder-be-s5-01) (categoria da equipe e tipo de cada integrante). A BE-S5-02 (cadastro da equipe e dos integrantes em um fluxo, com ativação própria de quem não tem conta) é de outra entrega: aqui o convidado usa o cadastro que já existe (`POST /auth/cadastro`) e esta tarefa cuida do que vem depois.

Decisões da reunião de 05/11/2026 têm precedência operacional provisória sobre o documento da Sprint 2. A regra de elegibilidade de profissionais e mistos **ainda precisa de validação formal com o Squad 1** (veja "Política da edição").

## O que a pessoa declara e o que o conferente verifica

| Autodeclaração | Comprovação |
|----------------|-------------|
| O que a própria pessoa **afirma**: `ESTUDANTE` (instituição, curso, período) ou `PROFISSIONAL` (organização, cargo). Tabela `autodeclaracoes_vinculo`, só de inserção. | O que o conferente **verificou** em um documento: comprovante `APROVADO` do tipo certo (`comprovantes_vinculo.tipo_vinculo`). |
| Não prova nada e nunca vira "aprovada". | Só ele faz `vinculo_comprovado` ser verdadeiro. |

A resposta de `GET /me/autodeclaracao` mostra as duas coisas lado a lado e nunca as mistura.

## Rotas

| Rota | Quem acessa | O que faz |
|------|-------------|-----------|
| `PUT /me/autodeclaracao` | Participante (e DEV), inclusive com a conta pendente | A pessoa declara o próprio vínculo na edição com inscrições abertas |
| `GET /me/autodeclaracao` | Participante (e DEV), inclusive com a conta pendente | Declaração atual, histórico e o comprovante que vale para a pessoa, com `vinculo_comprovado` |
| `POST /comprovantes` | Qualquer usuário logado (como antes) | Passa a registrar o **tipo** do vínculo (veja abaixo) |
| `GET /admin/comprovantes` e `POST /admin/comprovantes/{id}/aprovar` e `/recusar` | Organizador e Comitê Científico (e DEV, Q25) | Como antes; a fila traz `tipo_vinculo` e a `autodeclaracao` ligada, para comparar com o documento |

### Autorização estrita

- O usuário vem **sempre do token**. Não existe rota nem campo para declarar, enviar comprovante ou aceitar termos em nome de outra pessoa; o líder também não. Campos extras (`usuario_id`, `hackathon_id`, `status`, `termos_ids`...) dão 422.
- Os aceites de termos continuam individuais (`POST /convites/{id}/aceitar` e `POST /hackathons/{id}/termos/aceites` usam o usuário logado).
- Só participantes declaram: Organizador, Comitê e Mentor recebem 403. DEV segue a exceção do time.
- O líder indica o tipo de cada pessoa (BE-S5-01) e a pessoa **confirma com a própria conta**. Os dois podem divergir, e isso aparece como pendência (abaixo); nada é sobrescrito.

### Declarar

`PUT /me/autodeclaracao` aceita `tipo` e os campos desse tipo:

```json
{"tipo": "ESTUDANTE", "instituicao": "UFPA", "curso": "Sistemas de Informação", "periodo": 5}
{"tipo": "PROFISSIONAL", "organizacao": "Açaí Valley", "cargo": "Engenheira"}
```

Campos obrigatórios do tipo ausentes, campos do outro tipo ou valores em branco dão 422. Vale para a edição com inscrições abertas (a mesma do cadastro e do reenvio do comprovante); sem ela, 409.

**Auditoria.** Cada mudança grava uma linha nova com a data, e a anterior continua no histórico. Repetir a declaração atual não grava nada. Um trigger do banco impede alterar uma declaração gravada, mesmo fora da API (excluir segue possível, como na remoção de uma edição). Declarações simultâneas da mesma pessoa são serializadas: duas iguais viram uma só.

**Efeito na equipe.** Declarar reavalia a homologação da equipe da pessoa. Se o tipo declarado contradiz o que o líder indicou, a equipe sai da homologação (`TIPO_DIVERGENTE`) até o líder corrigir a composição (`PUT /equipes/{id}/composicao`) ou a pessoa rever a declaração. Como a pessoa pode se declarar a qualquer momento, isso é intencional: quem confirma é ela.

## Comprovante por tipo

O comprovante agora diz qual vínculo comprova (`tipo_vinculo`) e qual declaração ele sustenta (`autodeclaracao_id`, quando houver):

- **Quem decide o tipo é o servidor, não o pedido.** `POST /comprovantes` usa o tipo que o líder indicou, se a pessoa já está em uma equipe da edição; senão o que ela declarou; senão `ESTUDANTE`, como antes da tarefa. O pedido só traz o link.
- O limite de **um comprovante em aberto ou aprovado** passou a valer **por tipo** (`uq_comprovantes_vinculo_ativo` inclui `tipo_vinculo`). Quem muda de tipo precisa de um comprovante do tipo novo, mesmo com um aprovado do outro.
- Para a homologação **só vale o comprovante do tipo que o líder indicou**: um comprovante acadêmico aprovado não comprova o vínculo de quem é indicado como `PROFISSIONAL`.
- Recusa e reenvio funcionam como antes, dentro do tipo: o comprovante recusado fica no histórico, o motivo aparece em `GET /comprovantes/meus` e a pessoa envia outro.
- Os que já existiam eram acadêmicos e viram `ESTUDANTE`.
- O cadastro público (`POST /auth/cadastro`) continua registrando o comprovante inicial como `ESTUDANTE`. Um profissional ativa a conta e depois envia o comprovante profissional por `POST /comprovantes`. No cadastro por convite ([BE-S5-02](cadastro-equipe-integrantes.md)) o comprovante opcional já nasce com o tipo que o líder indicou no convite.

## Documentos privados

O link do documento (`arquivo_url`) só chega a quem enviou (`GET /comprovantes/meus`) e aos conferentes (`GET /admin/comprovantes`). Nunca aparece no painel da equipe, na composição, na listagem de membros, nos convites nem em `GET /me/autodeclaracao` (que traz só `ComprovacaoResumo`, sem o link). Os testes conferem cada uma dessas respostas.

O arquivo em si fica em um serviço externo; a API guarda só o link. Se o serviço externo aceitar o link sem autenticação, quem o conhecer consegue abrir o arquivo: restringir o acesso ao documento é configuração desse serviço, fora desta API.

## Política da edição (provisória)

Colunas novas em `hackathon`, ajustadas pelo Organizador em `PATCH /admin/hackathons/{id}`:

| Campo | Padrão | Efeito na homologação |
|-------|--------|-----------------------|
| `exige_autodeclaracao` | `false` | Exige a declaração de cada integrante (`AUTODECLARACAO_PENDENTE`). Nasce falso para não criar uma exigência nova em edições em andamento. |
| `exige_comprovante_estudante` | `true` | Exige comprovante `APROVADO` de quem é `ESTUDANTE`. |
| `exige_comprovante_profissional` | `true` | Exige comprovante `APROVADO` de quem é `PROFISSIONAL`. |

A equipe só é homologada com os requisitos **aplicáveis** a cada integrante cumpridos, por categoria:

| Categoria | O que a homologação confere (além de termos, tamanho e convites) |
|-----------|------------------------------------------------------------------|
| `ESTUDANTES` | Comprovante acadêmico aprovado de todos (como antes) |
| `PROFISSIONAIS` | Comprovante profissional aprovado de todos |
| `MISTA` | De cada pessoa, o comprovante do tipo que o líder indicou para ela |

Pendências individuais novas (no painel e em `GET /equipes/{id}/composicao`): `AUTODECLARACAO_PENDENTE` e `TIPO_DIVERGENTE`. As duas só pesam na homologação, não impedem o líder de concluir a inscrição. A composição traz, por pessoa, `tipo_declarado` e `vinculo_comprovado`, sem os dados da declaração.

**Pontos a validar formalmente com o Squad 1:** (1) se o profissional precisa de comprovante, de qual documento e quem o confere (hoje, o mesmo fluxo e os mesmos conferentes do estudante, Q25); (2) se a autodeclaração é obrigatória para homologar; (3) o que fazer quando o tipo declarado diverge do indicado (hoje bloqueia até alguém corrigir).

## Compatibilidade

- Migration `V202611161400__autodeclaracao_comprovantes.sql`: tabela `autodeclaracoes_vinculo`, `comprovantes_vinculo.tipo_vinculo` e `autodeclaracao_id`, e as três colunas de política.
- Sem as flags novas e sem declarações, nada muda: comprovantes existentes são `ESTUDANTE`, as equipes são `ESTUDANTES` e as mensagens de pendência do estudante são as de sempre.
- As respostas só ganharam campos: `tipo_vinculo` e `autodeclaracao_id` no comprovante, `autodeclaracao` na fila do conferente, `tipo_declarado` no painel e `tipo_declarado` e `vinculo_comprovado` na composição.

---

[← Voltar ao README](../README.md)
