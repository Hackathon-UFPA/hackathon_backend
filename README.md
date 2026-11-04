Hackathon Backend
=================

API do sistema de gestão de hackathons da UFPA, construída com **FastAPI**. Cuida do cadastro e login, das equipes e convites, da inscrição e homologação, das propostas, dos temas e rubricas, da distribuição de propostas, do registro da avaliação científica e da homologação e divulgação do resultado.

## Stack

- **FastAPI** + **SQLModel** (async)
- **PostgreSQL 17** com migrations em **Flyway**
- **Poetry** para dependências (Python 3.13)
- **Docker Compose** para rodar tudo localmente
- **Ruff** (lint e formatação) e **pytest** (testes)
- **GitHub Actions** para CI e deploy

## Documentação

- [Contratos da API](docs/api-contratos.md): Swagger, autenticação e formato dos erros
- [Autenticação e permissões](docs/autenticacao.md): cadastro, login, perfis e guia para o front
- [Convites e termos](docs/convites-e-termos.md)
- [Equipes e membros](docs/equipes-e-membros.md)
- [Inscrição e homologação](docs/inscricao-e-homologacao.md)
- [Propostas](docs/propostas.md): envio definitivo e protocolo
- [Temas e rubrica](docs/temas-e-rubrica.md)
- [Avaliação](docs/avaliacao.md): distribuição e registro da avaliação científica pela rubrica
- [Resultado](docs/resultado.md): homologação do resultado e propostas aprovadas públicas
- [Banco de dados](docs/banco-de-dados.md): tabelas, enums e migrations
- [Guia de desenvolvimento](docs/desenvolvimento.md): como criar rotas, comandos e CI/CD

Com a API no ar, a documentação interativa das rotas fica em `http://localhost:8000/docs`.

## Situação atual

| Módulo                                  | Requisitos         | Situação  |
|-----------------------------------------|--------------------|-----------|
| Estrutura do projeto, Docker e CI       | —                  | Concluído |
| Autenticação, perfis e cadastro de usuários | RF01, RF02, RF06 a RF08 | Concluído |
| Convites, aceite de participação e termos | RF18 a RF20      | Concluído |
| Equipes e membros                       | RF18, RF24         | Concluído |
| Comprovantes, inscrição e homologação   | RF21 a RF23, RF25  | Concluído |
| Rascunho e envio da proposta            | RF26 a RF28        | Concluído |
| Temas e rubrica de avaliação            | RF15 a RF17        | Concluído |
| Distribuição de propostas aos avaliadores | RF29             | Concluído |
| Avaliação científica pela rubrica       | RF30, BE-S4-10     | Concluído |
| Homologação do resultado e aprovadas    | RF31, RF32, BE-S4-11 | Concluído |
| Envio de e-mails e notificações         | —                  | Pendente  |

## Requisitos

- Docker com o plugin `docker compose`
- `make` (opcional): é só um atalho. Cada comando tem o equivalente em `docker compose` no [Guia de desenvolvimento](docs/desenvolvimento.md#comandos). No Windows o `make` não vem instalado.

## Instalação

```bash
git clone https://github.com/Hackathon-UFPA/hackathon_backend.git
cd hackathon_backend
make env    # cria o .env a partir do .env.example
make up     # sobe db, flyway (migrations), app e pgadmin
```

Sem o `make`, os dois comandos são:

```bash
cp .env.example .env
docker compose up -d --build
```

Para criar o primeiro Organizador (só ele cadastra os demais perfis), veja [Autenticação e permissões](docs/autenticacao.md).

## Uso

Depois do `make up`, estes serviços ficam disponíveis:

| Serviço       | Endereço                        | Acesso                                       |
|---------------|---------------------------------|----------------------------------------------|
| API (Swagger) | http://localhost:8000/docs      | —                                            |
| Health        | http://localhost:8000/health    | —                                            |
| pgAdmin       | http://localhost:`PGADMIN_PORT` | `admin@example.com` / `admin`                |
| Postgres      | `localhost:POSTGRES_PORT`       | `postgres` / `postgres`, banco `POSTGRES_DB` |

- No pgAdmin, registre o servidor com host **`db`** e porta **`5432`** (ele roda dentro da rede do Docker).
- Pelo terminal, `make db-shell` abre o `psql` já conectado.
- **Portas ocupadas?** Mude `POSTGRES_PORT`, `PGADMIN_PORT` e `APP_PORT` no `.env` (ex.: 5434 e 4041) e rode `make up` de novo.

### Comandos principais

| Comando         | O que faz                                          |
|-----------------|----------------------------------------------------|
| `make up`       | Sobe os containers (com build)                     |
| `make down`     | Para os containers                                 |
| `make logs`     | Acompanha os logs da API                           |
| `make migrate`  | Aplica as migrations pendentes                     |
| `make test`     | Roda o pytest no banco de testes                   |
| `make lint`     | Ruff: lint e checagem de formatação                |
| `make format`   | Corrige lint e formata o código                    |
| `make clean`    | Para tudo e **apaga os dados do banco**            |

A lista completa, com o equivalente sem `make`, está no [Guia de desenvolvimento](docs/desenvolvimento.md#comandos).

### Testes

Os testes usam outro banco, o `<POSTGRES_DB>_test` (ex.: `app_db_test`), criado e migrado pelo `docker compose`. O `pytest` troca para ele sozinho, então rodar os testes nunca mexe nos dados de desenvolvimento.

```bash
make test
```

## Estrutura do projeto

```
.
├── app/
│   ├── main.py            # cria o FastAPI, CORS e inclui os routers
│   ├── __init__.py        # tags do Swagger
│   ├── const/             # variáveis de ambiente (config.py) e enums
│   ├── db/                # engine e get_session
│   ├── models/            # tabelas SQLModel (1 arquivo por tabela)
│   ├── schemas/           # Pydantic: XCreate, XUpdate, XResponse
│   ├── controllers/       # acesso ao banco
│   ├── views/             # routers FastAPI (rotas e Swagger)
│   ├── services/          # regras de negócio e transações
│   ├── validations/       # validações reutilizáveis
│   ├── security/          # senha (Argon2), token JWT e permissões por perfil
│   ├── exceptions/        # HTTPException padronizadas
│   ├── scripts/           # tarefas de apoio (ex.: criar o primeiro Organizador)
│   ├── middlewares/
│   ├── integrations/      # clientes de APIs externas
│   ├── jobs/              # tarefas agendadas
│   └── utils/             # lifespan, openapi e helpers genéricos
├── migrations/            # SQL do Flyway
├── tests/
├── docs/                  # documentação por assunto e diagramas
├── Dockerfile             # targets: dev (compose) e prod (deploy)
├── Dockerfile.flyway      # imagem com as migrations para o deploy
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

Fluxo de uma requisição:

```
view (rota) → service (regras) → controller (banco) → model (tabela)
     ↑ valida entrada e saída com schemas
```

## CI/CD

- `.github/workflows/ci.yml`: a cada push na `main` ou `dev` e em todo PR, sobe o Postgres, aplica as migrations, roda o Ruff e o pytest.
- `.github/workflows/deploy.yml`: deploy manual (`workflow_dispatch`) em servidor com runner self-hosted. **Nunca coloque senhas direto no workflow.**

## Fluxo de contribuição

1. Crie uma branch a partir da `main`, com o código da tarefa: `feat/be-s4-13-contratos-api`.
2. Faça commits pequenos, com prefixo e mensagem em português: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
3. Rode `make lint` e `make test` antes de abrir o PR.
4. Abra o Pull Request para a `main`. O CI precisa passar.
5. Migrations já aplicadas nunca são editadas: crie uma nova.

## Equipe

Squad 3 (Backend) do Hackathon UFPA: Danilo Sovano, Esdras Silva, Hiago Silva, Thiago Leonardo e Yasmim Nagat.
