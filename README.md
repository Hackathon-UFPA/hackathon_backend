# Template FastAPI

Modelo de backend com **FastAPI + SQLModel (async) + PostgreSQL 17 + Flyway + Poetry + Docker Compose**, na mesma arquitetura do SAIA.

## Começando um projeto novo

1. No GitHub, clique em **Use this template → Create a new repository** (ou clone e apague o `.git`):
   ```bash
   git clone <url-do-template> meu-projeto
   cd meu-projeto
   rm -rf .git && git init
   ```
2. Troque o nome do projeto:
   - `pyproject.toml` → `name`
   - `.env.example` → `COMPOSE_PROJECT_NAME`, `API_TITLE`, `POSTGRES_DB`
3. Crie o `.env` e suba tudo:
   ```bash
   make env    # cria o .env a partir do .env.example
   make up     # sobe db, flyway, app e pgadmin
   ```
4. Acesse:
   - API: http://localhost:8000/docs
   - Health: http://localhost:8000/health
   - pgAdmin: http://localhost:4040 (host do banco: `db`)

> Para rodar ao mesmo tempo que outro projeto, mude `APP_PORT`, `POSTGRES_PORT` e `PGADMIN_PORT` no `.env`.

## Estrutura

```
.
├── app/
│   ├── main.py            # cria o FastAPI, CORS e inclui os routers
│   ├── __init__.py        # tags do Swagger
│   ├── logging_config.py
│   ├── const/             # config.py (variáveis de ambiente), enums, constantes
│   ├── db/                # engine e get_session
│   ├── models/            # tabelas SQLModel (1 arquivo por tabela)
│   ├── schemas/           # Pydantic de entrada/saída (XCreate, XResponse)
│   ├── controllers/       # acesso ao banco (get/criar/atualizar/deletar)
│   ├── views/             # routers FastAPI; views/__init__.py agrega todos
│   ├── services/          # regras de negócio que juntam vários controllers
│   ├── validations/       # validações reutilizáveis
│   ├── security/          # autenticação/autorização
│   ├── exceptions/        # HTTPException padronizadas (404, constraint, 500)
│   ├── middlewares/
│   ├── integrations/      # clientes de APIs externas
│   ├── jobs/              # tarefas agendadas (iniciar no lifespan)
│   └── utils/             # lifespan, helpers genéricos
├── migrations/            # SQL do Flyway
├── tests/
├── Dockerfile             # targets: dev (compose) e prod (deploy)
├── Dockerfile.flyway      # imagem com as migrations para o deploy
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

### Fluxo de uma requisição

```
view (rota) → controller (banco) → model (tabela)
     ↑ valida entrada/saída com schemas
```

## Criando uma entidade nova (ex.: `produto`)

1. **Migration** — `migrations/V<AAAAMMDDHHMM>__criar_tabela_produto.sql`:
   ```sql
   CREATE TABLE produto (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       nome VARCHAR(255) NOT NULL
   );
   ```
2. **Model** — `app/models/produto.py` (`class Produto(SQLModel, table=True)`), espelhando a tabela.
3. **Schemas** — `app/schemas/produto.py` (`ProdutoCreate`, `ProdutoResponse`).
4. **Controller** — `app/controllers/produto.py` (`get_produto_by_id`, `criar_produto`, ...), usando `app/exceptions/db.py` para os erros.
5. **View** — `app/views/produto.py` com `router = APIRouter(prefix="/produtos", tags=["Produtos"])`.
6. Registrar o router em `app/views/__init__.py` e a tag em `app/__init__.py`.
7. `make migrate` para aplicar a migration.

## Migrations (Flyway)

- Nome: `V<AAAAMMDDHHMM>__descricao.sql` (ex.: `V202610111530__adicionar_coluna_preco.sql`).
- **Nunca edite uma migration já aplicada**; crie uma nova.
- Em dev, o compose roda as migrations ao subir. Para aplicar sem reiniciar: `make migrate`.

## Comandos

| Comando        | O que faz                                         |
|----------------|---------------------------------------------------|
| `make env`     | Cria o `.env` a partir do `.env.example`          |
| `make up`      | Sobe os containers (com build)                    |
| `make down`    | Para os containers                                |
| `make restart` | Reinicia                                          |
| `make logs`    | Acompanha os logs da API                          |
| `make migrate` | Aplica migrations pendentes                       |
| `make test`    | Roda o pytest dentro do container                 |
| `make lint`    | Ruff (lint + checagem de formatação)              |
| `make format`  | Corrige lint e formata o código                   |
| `make shell`   | Terminal dentro do container da API               |
| `make db-shell`| psql no banco                                     |
| `make lock`    | Atualiza o `poetry.lock` após editar dependências |
| `make clean`   | Para tudo e **apaga os dados do banco**           |

### Adicionando dependências

Edite o `pyproject.toml`, rode `make lock` e depois `make up` para reconstruir a imagem.

## CI/CD (GitHub Actions)

- `.github/workflows/ci.yml` — a cada push/PR: sobe Postgres, aplica migrations, roda ruff e pytest.
- `.github/workflows/deploy.yml` — deploy manual (workflow_dispatch) em servidor com runner self-hosted: build da imagem `prod`, `flyway repair` + `migrate` e sobe o container. Configure os secrets/variables listados no topo do arquivo. **Nunca coloque senhas direto no workflow.**
