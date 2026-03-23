# CodeClaw

Initial Phase 1 backend scaffold for the PRD in [`docs/PRD.md`](docs/PRD.md).

Current implementation status is tracked in [`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md).
Configuration is described in [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## Run

1. Install dependencies:

   ```bash
   pip install -e .
   ```

2. Start the API:

   ```bash
   uvicorn app.main:app --reload
   ```

## Current scope

This bootstrap includes:

- FastAPI app skeleton
- predefined project registry loaded from TOML
- task creation and state transitions
- in-memory orchestration and run tracking
- per-task git worktree isolation
- SSE task event stream

Projects are loaded from `~/.codeclaw/config.toml` with optional per-project metadata under `~/.codeclaw/projects/<project-id>/`.
