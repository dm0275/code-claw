PYTHON := venv/bin/python
PIP := venv/bin/pip
PYTEST := venv/bin/pytest
RUFF := venv/bin/ruff
MYPY := venv/bin/mypy
UVICORN := venv/bin/uvicorn
DOCKER_COMPOSE := docker compose
ALEMBIC := venv/bin/alembic

.PHONY: install install-dev run run-dev lint test test-postgres db-up db-down db-logs db-ps db-migrate db-current

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[dev]"

run:
	$(UVICORN) app.main:app --reload

run-dev:
	$(UVICORN) app.main:app --reload

lint:
	$(RUFF) check app --fix
	$(MYPY) app

test:
	$(PYTEST)

test-postgres: db-up
	$(PYTEST) -m postgres_integration tests/test_postgres_integration.py

db-up:
	$(DOCKER_COMPOSE) up -d --wait postgres

db-down:
	$(DOCKER_COMPOSE) down

db-logs:
	$(DOCKER_COMPOSE) logs -f postgres

db-ps:
	$(DOCKER_COMPOSE) ps

db-migrate:
	$(ALEMBIC) upgrade head

db-current:
	$(ALEMBIC) current
