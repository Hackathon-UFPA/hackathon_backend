[← Voltar ao README](../README.md)

# Guia de desenvolvimento

## Criando as rotas de uma entidade (ex.: `equipe`)

Ao criar uma nova entidade, siga a separação usada por `equipe`:

1. **Controller** — consultas e persistência sem commit, como `app/controllers/equipe.py`; `atualizar_instancia` (em `app/utils/generic_db_operations.py`) copia somente os campos enviados no schema.
2. **Service** — regras, autorização e transação, como `app/services/equipe.py`, usando as exceções de negócio e `app/exceptions/db.py` para erros de integridade.
3. **View** — contrato HTTP e documentação Swagger, como `app/views/equipe.py`, recebendo `EquipeCreate`/`EquipeUpdate` e devolvendo `EquipeResponse`.
4. Registrar o router em `app/views/__init__.py` e a tag em `app/__init__.py`.

Para uma tabela nova: migration → model em `app/models/` (e importar em `models/__init__.py`) → schemas → passos acima.

## Comandos

Cada alvo do `Makefile` é um atalho para o comando `docker compose` da coluna ao lado — use a que preferir.

| Comando         | Equivalente sem `make`                                                              | O que faz                                         |
|-----------------|-------------------------------------------------------------------------------------|---------------------------------------------------|
| `make env`      | `cp .env.example .env`                                                              | Cria o `.env` a partir do `.env.example`          |
| `make up`       | `docker compose up -d --build`                                                      | Sobe os containers (com build)                    |
| `make down`     | `docker compose down`                                                               | Para os containers                                |
| `make restart`  | `docker compose down && docker compose up -d --build`                               | Reinicia                                          |
| `make logs`     | `docker compose logs -f app`                                                        | Acompanha os logs da API                          |
| `make migrate`  | `docker compose run --rm flyway` e `docker compose run --rm flyway_test`            | Aplica migrations pendentes nos dois bancos       |
| `make test`     | `docker compose exec app pytest`                                                    | Roda o pytest no banco de testes, dentro do container |
| `make lint`     | `docker compose exec app ruff check .` e `docker compose exec app ruff format --check .` | Ruff (lint + checagem de formatação)         |
| `make format`   | `docker compose exec app ruff check --fix .` e `docker compose exec app ruff format .` | Corrige lint e formata o código                |
| `make shell`    | `docker compose exec app bash`                                                      | Terminal dentro do container da API               |
| `make db-shell` | `docker compose exec db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'`              | psql no banco                                     |
| `make lock`     | `docker run --rm -v "$PWD":/code -w /code python:3.13-slim sh -c 'pip install -q poetry==2.1.3 && poetry lock'` | Atualiza o `poetry.lock` após editar dependências |
| `make clean`    | `docker compose down -v`                                                            | Para tudo e **apaga os dados do banco**           |

No PowerShell o `&&` não existe: rode cada comando em uma linha separada e troque `$PWD` por `${PWD}`.

Para adicionar uma dependência: edite o `pyproject.toml`, rode `make lock` (ou o equivalente) e depois `make up`.

## CI/CD (GitHub Actions)

- `.github/workflows/ci.yml` — a cada push/PR em `main`/`dev`: sobe Postgres, aplica as migrations, roda ruff e pytest.
- `.github/workflows/deploy.yml` — deploy manual (workflow_dispatch) em servidor com runner self-hosted. Configure os secrets/variables listados no topo do arquivo. **Nunca coloque senhas direto no workflow.**

---

[← Voltar ao README](../README.md)
