[← Voltar ao README](../README.md)

# Contratos da API

Resumo do que a interface (front) precisa saber para consumir a API. O detalhe de cada rota, com campos, exemplos e erros, está no **Swagger** (`/docs`); o contrato em JSON está em `/openapi.json`.

## Como usar o Swagger

1. Abra `http://localhost:8000/docs` (com a API no ar).
2. Rotas agrupadas por assunto: Health, Autenticação, Usuários, Equipes, Convites, Termos, Comprovantes, Inscrição, Propostas, Temas, Rubrica e Avaliação.
3. Cada rota mostra resumo, descrição, quem pode acessar, exemplo de corpo e a lista de erros possíveis.
4. Para testar rotas protegidas: faça `POST /auth/login`, copie o `access_token`, clique em **Authorize** e cole o token.

## Autenticação

Todas as rotas, exceto as públicas, exigem o cabeçalho:

```
Authorization: Bearer <access_token>
```

| Rota pública                          | Uso                                         |
|---------------------------------------|---------------------------------------------|
| `GET /health`                         | Verifica a API e o banco                    |
| `POST /auth/cadastro`                 | Cadastro do participante                    |
| `POST /auth/login`                    | Login, devolve o token e os dados do usuário |
| `GET /hackathons/{id}/rubrica`        | Rubrica publicada                           |

O fluxo completo (cadastro, login, conta pendente, perfis) está em [Autenticação e permissões](autenticacao.md).

## Formato dos erros

Todo erro de regra de negócio tem o mesmo corpo:

```json
{ "detail": "Mensagem explicando o problema" }
```

A única exceção é o **422** de validação do FastAPI, em que `detail` é uma lista. `loc` aponta o campo e `msg` explica o problema:

```json
{
  "detail": [
    { "loc": ["body", "senha"], "msg": "Value error, a senha precisa ter letra e número", "type": "value_error" }
  ]
}
```

| Código | Significado                                         | Quando acontece                                                                 |
|--------|-----------------------------------------------------|---------------------------------------------------------------------------------|
| 400    | Violação de integridade no banco                    | Valor repetido ou referência inexistente que escapou das regras do service      |
| 401    | Não autenticado                                     | Sem token, token inválido ou vencido, conta desativada, e-mail ou senha errados |
| 403    | Sem permissão                                       | Perfil não pode usar a rota, ou conta pendente em rota que exige conta ativa    |
| 404    | Não encontrado                                      | Recurso inexistente, ou que a pessoa não pode ver (não revela que existe)       |
| 409    | Conflito com o estado atual                         | Prazo fora da janela, e-mail repetido, equipe não homologada, reenvio, etc.     |
| 422    | Dado inválido                                       | Campo fora do formato ou regra de validação                                     |
| 429    | Muitas tentativas                                   | Conta bloqueada após falhas de login; o cabeçalho `Retry-After` traz os segundos |
| 500    | Erro interno                                        | Falha inesperada                                                                |

Cada rota lista no Swagger os códigos que ela pode devolver.

## Convenções dos contratos

- **IDs** são UUID.
- **Datas e horas** estão em UTC, no formato ISO 8601.
- **Enums** são sempre em MAIÚSCULO (ex.: `PARTICIPANTE`, `HOMOLOGADA`). Veja os valores em [Banco de dados](banco-de-dados.md#enums).
- **Campos desconhecidos** são recusados com 422 nas rotas de equipes, membros, propostas e avaliação.

## Documentação por assunto

| Assunto                         | Arquivo                                                     |
|---------------------------------|-------------------------------------------------------------|
| Cadastro, login e permissões    | [autenticacao.md](autenticacao.md)                          |
| Convites e termos               | [convites-e-termos.md](convites-e-termos.md)                |
| Equipes e membros               | [equipes-e-membros.md](equipes-e-membros.md)                |
| Comprovantes, inscrição e homologação | [inscricao-e-homologacao.md](inscricao-e-homologacao.md) |
| Rascunho e envio da proposta    | [propostas.md](propostas.md)                                |
| Temas e rubrica                 | [temas-e-rubrica.md](temas-e-rubrica.md)                    |
| Distribuição e avaliação científica | [avaliacao.md](avaliacao.md)                             |

---

[← Voltar ao README](../README.md)
