# Implementation Progress

This document tracks what has been implemented from the PRD, what has been verified, and what remains next.

## Current Status

Date: 2026-03-28

Phase in progress: Phase 1, Core Backend

Overall state:

- Project bootstrapped as a Python package with FastAPI
- Initial backend API implemented
- Predefined project registry introduced for execution safety
- Project registration through the app/API added for local repositories
- Postgres-backed persistence introduced for runtime state
- Alembic migration tooling introduced for schema evolution
- Durable task artifact capture introduced for review and auditability
- Local developer workflow added
- Functional backend tests expanded and passing

## Implemented

### Backend scaffold

- FastAPI application created in `app/main.py`
- Packaging metadata added in `pyproject.toml`
- Basic run instructions added in `README.md`
- `Makefile` added for common developer commands

### Domain model

- Project models
- Task models
- Run models
- Approval request model
- Task event model

### API endpoints

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

### Task orchestration

- SQL-backed store for tasks, runs, and approvals
- In-memory event fanout for recent task events
- Prompt builder aligned to the PRD structure:
  - objective
  - project
  - constraints
  - acceptance criteria
  - output expectations
- Project-specific TOML context and `instructions.md` merged into prompts
- Background task execution via thread-based runner dispatch
- Task lifecycle handling:
  - `pending`
  - `running`
  - `awaiting_approval`
  - `completed`
  - `failed`
  - `rejected`

### Execution layer

- Project path validation
- Codex CLI runner wired through `codex exec --json`
- Per-task git worktree creation before execution
- Real-time stdout and stderr streaming into task events
- Final agent message captured as task summary
- Changed files collected from `git status --short`
- Durable artifact capture for:
  - `diff.patch`
  - `stdout.jsonl`
  - `stderr.jsonl`
- Durable stdout and stderr artifacts exposed through the API
- Approval applies the isolated task diff back to the base project checkout
- Reject and failure paths clean up task worktrees
- SSE-compatible event formatting for live task updates

### Developer workflow

- `make install`
- `make install-dev`
- `make db-up`
- `make db-down`
- `make db-migrate`
- `make db-current`
- `make run`
- `make lint`
- `make test`

### Quality tooling

- Ruff configured for import sorting and basic lint checks
- Mypy configured for package-level type checking on the backend app

### Persistence

- SQLAlchemy-based runtime persistence
- PostgreSQL selected as the primary database target
- SQLite-compatible test path for persistence tests
- Live Postgres integration test path added via temporary test databases and Alembic migrations
- Durable task event persistence added for restart-safe task history
- Local Postgres compose file pinned to `postgres:16.8-alpine`
- Alembic-based schema migrations for runtime state and run artifact metadata
- Artifact file storage rooted under `~/.codeclaw/state/artifacts/`

## Verified

The following has been validated locally:

- Python modules compile successfully
- FastAPI, Uvicorn, and Pydantic dependencies install correctly in the project virtualenv
- Application imports successfully
- Automated tests pass
- SQL-backed task and run persistence works across store re-creation
- SQL-backed task event history works across store re-creation
- Alembic migration application works against a temporary SQLite database

Most recent verification:

- `make lint`
- Result: passed
- `make test`
- Result: `17 passed`
- `make test-integration`
- Result: `1 passed`
- `venv/bin/alembic upgrade head`
- Result: passed against a temporary SQLite database

## Current Limitations

These PRD items are not implemented yet:

- Clear extraction of the reusable Codex harness from the CodeClaw app shell
- Authentication
- Metrics and observability
- Web UI
- Docker-based isolation

## Next Recommended Work

Priority order:

1. Refactor toward a reusable Codex harness boundary inside the repository
2. Start the web UI once the execution contract stabilizes

## Change Log

### 2026-03-23

- Created initial FastAPI backend scaffold
- Added in-memory orchestration services
- Added SSE task event stream
- Added Python packaging and editable install support
- Added `Makefile`
- Added pytest-based API tests
- Added Ruff and Mypy lint workflow
- Replaced the stubbed runner with a Codex CLI-backed executor
- Added TOML-backed predefined project configuration
- Added per-task git worktree isolation and approval-time patch application
- Added SQL-backed persistence for tasks, runs, and approvals
- Added expanded functional test coverage and DB lifecycle Make targets
- Added Alembic migration tooling and the initial runtime-state migration
- Added this implementation progress tracker

### 2026-03-28

- Added durable task artifact capture for diffs and Codex output logs
- Added `GET /tasks/{task_id}/diff`
- Added Alembic migration for run artifact paths
- Renamed migration files to ordered `0001_...` and `0002_...` format
- Refreshed README and progress documentation to match the current backend
- Added a dedicated live-Postgres integration test path with temporary database setup and teardown
- Added durable SQL-backed task event persistence and restart-safe event history coverage
- Added API endpoints for durable stdout and stderr task artifacts
- Documented the decision to separate local project registration from optional future clone/import support
- Added local project registration endpoints and config persistence for existing git repositories
- Documented the intended reusable Codex harness boundary versus the CodeClaw-specific app shell
