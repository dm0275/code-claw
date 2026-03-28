PYTHON := venv/bin/python
PIP := venv/bin/pip
PYTEST := venv/bin/pytest
RUFF := venv/bin/ruff
MYPY := venv/bin/mypy
UVICORN := venv/bin/uvicorn
DOCKER_COMPOSE := docker compose
ALEMBIC := venv/bin/alembic

.DEFAULT_GOAL := help

.PHONY: help install install-dev start run run-dev lint test test-integration db-up db-down db-logs db-ps db-migrate db-current

help: ## List available make targets
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "%-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the package in editable mode
	$(PIP) install -e .

install-dev: ## Install the package with development dependencies
	$(PIP) install -e ".[dev]"

start: db-up db-migrate ## Start local Postgres, apply migrations, and run the API
	$(UVICORN) app.main:app --reload

run: ## Start the API with auto-reload
	$(UVICORN) app.main:app --reload

run-dev: ## Start the API with auto-reload for development
	$(UVICORN) app.main:app --reload

lint: ## Run Ruff and Mypy checks
	$(RUFF) check app --fix
	$(MYPY) app

test: ## Run the default test suite under tests/unit
	$(PYTEST) tests/unit

test-integration: db-up ## Run integration tests under tests/integration
	$(PYTEST) tests/integration/test_postgres_integration.py

db-up: ## Start the local Postgres container and wait for readiness
	$(DOCKER_COMPOSE) up -d --wait postgres

db-down: ## Stop the local Postgres container
	$(DOCKER_COMPOSE) down

db-logs: ## Follow logs for the local Postgres container
	$(DOCKER_COMPOSE) logs -f postgres

db-ps: ## Show local Postgres container status
	$(DOCKER_COMPOSE) ps

db-migrate: ## Apply Alembic migrations to the configured database
	$(ALEMBIC) upgrade head

db-current: ## Show the current Alembic revision
	$(ALEMBIC) current
