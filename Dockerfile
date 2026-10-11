# ---------- base: Python + Poetry ----------
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.1.3 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /code
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"
COPY pyproject.toml poetry.lock ./

# ---------- dev: todas as dependências + reload (usado pelo docker compose) ----------
FROM base AS dev

RUN poetry install --no-root
ENV PATH="/code/.venv/bin:$PATH"

COPY app ./app
COPY tests ./tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------- build: só dependências de produção ----------
FROM base AS build

RUN poetry install --no-root --only main

# ---------- prod: imagem final enxuta, sem Poetry, usuário não-root ----------
FROM python:3.13-slim AS prod

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/code/.venv/bin:$PATH"

WORKDIR /code
RUN useradd --create-home --uid 1000 appuser

COPY --from=build /code/.venv ./.venv
COPY app ./app

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
