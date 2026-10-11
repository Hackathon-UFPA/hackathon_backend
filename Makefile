.PHONY: env up down restart logs migrate test lint format shell db-shell lock clean

env:
	cp -n .env.example .env

up:
	docker compose up -d --build

down:
	docker compose down

restart: down up

logs:
	docker compose logs -f app

# Roda as migrations pendentes sem reiniciar a API
migrate:
	docker compose run --rm flyway

test:
	docker compose exec app pytest

lint:
	docker compose exec app ruff check .
	docker compose exec app ruff format --check .

format:
	docker compose exec app ruff check --fix .
	docker compose exec app ruff format .

shell:
	docker compose exec app bash

db-shell:
	docker compose exec db sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

# Atualiza o poetry.lock depois de mexer no pyproject.toml (não precisa de Poetry instalado)
lock:
	docker run --rm -v "$$PWD":/code -w /code python:3.13-slim \
		sh -c 'pip install -q poetry==2.1.3 && poetry lock'

# Para tudo e APAGA os dados do banco
clean:
	docker compose down -v
