# CodeClaw

Initial Phase 1 backend scaffold for the PRD in [`docs/PRD.md`](docs/PRD.md).

Current implementation status is tracked in [`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md).
Configuration is described in [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).
Modeling conventions are described in [`docs/ARCHITECTURE_NOTES.md`](docs/ARCHITECTURE_NOTES.md).
Persistence reasoning is described in [`docs/PERSISTENCE_DECISION.md`](docs/PERSISTENCE_DECISION.md).

## Run

1. Install dependencies:

   ```bash
   pip install -e .
   ```

2. Start local Postgres:

   ```bash
   docker compose up -d postgres
   ```

3. Apply migrations:

   ```bash
   venv/bin/alembic upgrade head
   ```

4. Start the API:

   ```bash
   uvicorn app.main:app --reload
   ```

## Common Tasks

```bash
make db-up
make db-migrate
make run
make lint
make test
```

## Current scope

This bootstrap includes:

- FastAPI app skeleton
- predefined project registry loaded from TOML
- persisted task/run/approval state backed by SQLAlchemy
- Alembic-based schema migrations
- task creation and state transitions
- per-task git worktree isolation
- SSE task event stream

Projects are loaded from `~/.codeclaw/config.toml` with optional per-project metadata under `~/.codeclaw/projects/<project-id>/`.
Runtime state uses the database configured by `CODECLAW_DATABASE_URL` or `DATABASE_URL`, defaulting to the local Postgres container in [`compose.yaml`](compose.yaml).
