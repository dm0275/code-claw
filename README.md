# CodeClaw

Initial Phase 1 backend scaffold for the PRD in [`docs/PRD.md`](docs/PRD.md).

Current implementation status is tracked in [`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md).
End-to-end local usage is described in [`docs/USAGE.md`](docs/USAGE.md).
Configuration is described in [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).
Project onboarding direction is described in [`docs/PROJECT_REGISTRATION_PLAN.md`](docs/PROJECT_REGISTRATION_PLAN.md).
Modeling conventions are described in [`docs/ARCHITECTURE_NOTES.md`](docs/ARCHITECTURE_NOTES.md).
Reusable-runtime boundary notes are described in [`docs/CODEX_HARNESS_BOUNDARY.md`](docs/CODEX_HARNESS_BOUNDARY.md).
Persistence reasoning is described in [`docs/PERSISTENCE_DECISION.md`](docs/PERSISTENCE_DECISION.md).

## Quickstart

1. Install dependencies and developer tooling:

   ```bash
   make install-dev
   ```

2. Start local Postgres, apply migrations, and run the API:

   ```bash
   make start
   ```

3. Register at least one local git repository through the API.

   See [`docs/USAGE.md`](docs/USAGE.md) for the `POST /projects` flow and
   [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for the underlying config layout.

4. Read [`docs/USAGE.md`](docs/USAGE.md) for the actual task lifecycle:

- creating a task
- following task status and live events
- reviewing `diff`, `stdout`, and `stderr`
- approving or rejecting the task

## Common Tasks

```bash
make start
make db-up
make db-migrate
make run
make lint
make test
make test-integration
```

`make test-integration` starts the local Postgres container if needed, creates a temporary database, applies Alembic migrations to that database, runs the current integration test suite, and drops the temporary database afterward. Override the default local connection with `CODECLAW_TEST_POSTGRES_ADMIN_URL` or the `CODECLAW_TEST_POSTGRES_*` variables if your Postgres instance is elsewhere.

## Current API Surface

The current backend exposes:

- `GET /health`
- `GET /projects`
- `GET /projects/{project_id}`
- `POST /projects`
- `GET /tasks`
- `POST /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/diff`
- `GET /tasks/{task_id}/stdout`
- `GET /tasks/{task_id}/stderr`
- `POST /tasks/{task_id}/approval`
- `GET /tasks/{task_id}/events`

## Current scope

This bootstrap includes:

- FastAPI app skeleton
- predefined project registry loaded from TOML
- persisted task/run/approval state backed by SQLAlchemy
- Alembic-based schema migrations
- task creation and state transitions
- per-task git worktree isolation
- durable task artifacts for diff/stdout/stderr review
- SSE task event stream

Projects are loaded from `~/.codeclaw/config.toml` with optional per-project metadata under `~/.codeclaw/projects/<project-id>/`.
Runtime state uses the database configured by `CODECLAW_DATABASE_URL` or `DATABASE_URL`, defaulting to the local Postgres container in [`compose.yaml`](compose.yaml).
