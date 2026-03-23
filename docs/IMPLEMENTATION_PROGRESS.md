# Implementation Progress

This document tracks what has been implemented from the PRD, what has been verified, and what remains next.

## Current Status

Date: 2026-03-22

Phase in progress: Phase 1, Core Backend

Overall state:

- Project bootstrapped as a Python package with FastAPI
- Initial backend API implemented
- Predefined project registry introduced for execution safety
- Postgres-backed persistence introduced for runtime state
- Local developer workflow added
- Baseline automated tests added and passing

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
- `GET /tasks`
- `POST /tasks`
- `GET /tasks/{task_id}`
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
- Approval applies the isolated task diff back to the base project checkout
- Reject and failure paths clean up task worktrees
- SSE-compatible event formatting for live task updates

### Developer workflow

- `make install`
- `make install-dev`
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
- Local Postgres compose file pinned to `postgres:16.8-alpine`

## Verified

The following has been validated locally:

- Python modules compile successfully
- FastAPI, Uvicorn, and Pydantic dependencies install correctly in the project virtualenv
- Application imports successfully
- Automated tests pass
- SQL-backed task and run persistence works across store re-creation

Most recent verification:

- `make lint`
- Result: passed
- `make test`
- Result: `3 passed`

## Current Limitations

These PRD items are not implemented yet:

- Persistent storage
- Diff extraction from real file changes
- Artifact storage
- Authentication
- Metrics and observability
- Web UI
- Docker-based isolation

## Next Recommended Work

Priority order:

1. Add migrations and explicit schema evolution tooling
2. Capture full diffs and durable artifacts from task execution
3. Harden approval flow for dirty-base-repo and patch-conflict scenarios
4. Persist task events or formalize event-retention behavior
5. Start the web UI once the execution contract stabilizes

## Change Log

### 2026-03-22

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
- Added this implementation progress tracker
