# CodeClaw

Initial Phase 1 backend scaffold for the PRD in [`docs/PRD.md`](docs/PRD.md).

Current implementation status is tracked in [`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md).

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
- workspace registration
- task creation and state transitions
- in-memory orchestration and run tracking
- SSE task event stream

The Codex runner is intentionally stubbed for now and emits synthetic execution logs until the real CLI integration is wired in.
