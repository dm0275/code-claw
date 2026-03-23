PYTHON := venv/bin/python
PIP := venv/bin/pip
PYTEST := venv/bin/pytest
RUFF := venv/bin/ruff
MYPY := venv/bin/mypy
UVICORN := venv/bin/uvicorn
DOCKER_COMPOSE := docker compose

.PHONY: install install-dev run run-dev lint test db-up db-down db-logs db-ps

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

db-up:
	$(DOCKER_COMPOSE) up -d postgres

db-down:
	$(DOCKER_COMPOSE) down

db-logs:
	$(DOCKER_COMPOSE) logs -f postgres

db-ps:
	$(DOCKER_COMPOSE) ps
