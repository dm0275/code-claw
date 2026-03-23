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

2. Start the API:

   ```bash
   uvicorn app.main:app --reload
   ```

3. Start local Postgres when working on persistence:

   ```bash
   docker compose up -d postgres
   ```

## Current scope

This bootstrap includes:

- FastAPI app skeleton
- predefined project registry loaded from TOML
- persisted task/run/approval state backed by SQLAlchemy
- task creation and state transitions
- per-task git worktree isolation
- SSE task event stream

Projects are loaded from `~/.codeclaw/config.toml` with optional per-project metadata under `~/.codeclaw/projects/<project-id>/`.
Runtime state uses the database configured by `CODECLAW_DATABASE_URL` or `DATABASE_URL`, defaulting to the local Postgres container in [`compose.yaml`](compose.yaml).
