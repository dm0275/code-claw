PYTHON := venv/bin/python
PIP := venv/bin/pip
PYTEST := venv/bin/pytest
RUFF := venv/bin/ruff
MYPY := venv/bin/mypy
UVICORN := venv/bin/uvicorn

.PHONY: install install-dev run lint test

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[dev]"

run:
	$(UVICORN) app.main:app --reload

lint:
	$(RUFF) check app --fix
	$(MYPY) app

test:
	$(PYTEST)
