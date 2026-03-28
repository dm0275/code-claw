# Usage Guide

This guide explains how to run CodeClaw locally and use the current backend API end to end.

## Prerequisites

- Python 3.11+
- Docker Desktop or another working Docker daemon
- A local git repository you want CodeClaw to operate on
- The Codex CLI installed and available on your `PATH` for real task execution

## 1. Install And Start The Backend

From the repository root:

```bash
make install-dev
make start
```

The API listens on `http://127.0.0.1:8000` by default.

If you want to see the available local developer tasks:

```bash
make
```

## 2. Register Allowed Projects

CodeClaw only runs tasks against projects declared in its managed registry.

Register an existing local git repository through the API:

```bash
curl -s -X POST http://127.0.0.1:8000/projects \
  -H 'content-type: application/json' \
  -d '{
    "id": "code-claw",
    "name": "CodeClaw",
    "path": "/Users/dmancilla/git/code-claw",
    "default_branch": "main",
    "execution": {
      "sandbox": "workspace-write",
      "approval_required": true,
      "auto_create_branch": false,
      "extra_writable_dirs": []
    },
    "context": {
      "summary": "FastAPI backend for orchestrating Codex CLI tasks.",
      "extra_constraints": [],
      "instructions": "Prefer backend changes before UI work."
    }
  }'
```

The backend validates that the path exists and is a git repository, then writes the same TOML-backed config layout it already uses under `~/.codeclaw/`.

Optional per-project metadata still lives under `~/.codeclaw/projects/<project-id>/`.
See [CONFIGURATION.md](/Users/dmancilla/git/code-claw/docs/CONFIGURATION.md) for the underlying layout.

## 3. Verify The API Is Healthy

```bash
curl -s http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

List the registered projects:

```bash
curl -s http://127.0.0.1:8000/projects
```

Fetch one registered project:

```bash
curl -s http://127.0.0.1:8000/projects/<project-id>
```

If `/projects` returns an empty list, no projects have been registered yet.

## 4. Create A Task

Submit a task against a registered `project_id`:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks \
  -H 'content-type: application/json' \
  -d '{
    "project_id": "code-claw",
    "mode": "change",
    "prompt": "Document the Makefile targets",
    "constraints": ["Only touch Markdown files"],
    "acceptance_criteria": ["README explains the new targets"]
  }'
```

The response contains the new task record, including its `id`.

Task modes:

- `change`: default mode for repo-editing tasks. These can produce diffs and may require approval before changes are applied.
- `response`: answer-only mode. These should complete without file changes or approval.

Example response-only task:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks \
  -H 'content-type: application/json' \
  -d '{
    "project_id": "code-claw",
    "mode": "response",
    "prompt": "Who was the first president of the United States?"
  }'
```

## 5. Follow Task Progress

List all tasks:

```bash
curl -s http://127.0.0.1:8000/tasks
```

Fetch one task in detail:

```bash
curl -s http://127.0.0.1:8000/tasks/<task-id>
```

The task detail response includes:

- the task state
- the associated run record
- recent task events

Current task states:

- `pending`
- `running`
- `awaiting_approval`
- `completed`
- `failed`
- `rejected`

## 6. Stream Live Events

You can stream live server-sent events for a task:

```bash
curl -N http://127.0.0.1:8000/tasks/<task-id>/events
```

The event stream includes existing history first, then live updates.

Typical event types include:

- `status`
- `prompt`
- `log`
- `error`
- `heartbeat`

## 7. Review Generated Artifacts

Once a `change` task reaches `awaiting_approval`, CodeClaw has captured durable review artifacts.

Get the patch:

```bash
curl -s http://127.0.0.1:8000/tasks/<task-id>/diff
```

Get captured stdout:

```bash
curl -s http://127.0.0.1:8000/tasks/<task-id>/stdout
```

Get captured stderr:

```bash
curl -s http://127.0.0.1:8000/tasks/<task-id>/stderr
```

These endpoints return plain text and respond with `404` if the artifact is not available.
That is expected for `response` tasks because they should not produce diffs.

## 8. Approve Or Reject A Task

Approve a task:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks/<task-id>/approval \
  -H 'content-type: application/json' \
  -d '{"action":"approve"}'
```

Reject a task:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks/<task-id>/approval \
  -H 'content-type: application/json' \
  -d '{"action":"reject"}'
```

Behavior today:

- Approval applies the isolated worktree diff back onto the base project checkout.
- Rejection discards the isolated task workspace.
- Approval fails with `409` if the base checkout has uncommitted changes.
- Approval fails with `409` if the patch cannot be applied cleanly.
- Approval fails with `503` if the runtime database schema is out of date.

If approval returns a schema error, run:

```bash
make db-migrate
```

## 9. Understand The Current Execution Model

The current backend flow is:

1. Validate the requested project against the predefined registry.
2. Create a per-task git worktree.
3. Build a structured prompt from the task plus project metadata.
4. Run Codex in the isolated worktree.
5. Capture task events plus durable review artifacts.
6. For `change` tasks, wait for explicit approval before applying changes to the base checkout.
7. For `response` tasks, complete immediately if the runner produces no file changes.

Important operational constraints:

- CodeClaw does not execute against arbitrary paths.
- The target project must already be a git repository.
- `response` tasks must not modify files. The harness fails them if the runner edits the workspace.
- The base checkout must be clean before approval can apply changes for `change` tasks.
- Task event history, runs, approvals, and artifacts are durable.

## 10. Run Tests

Default unit-oriented suite:

```bash
make test
```

Integration suite:

```bash
make test-integration
```

The integration suite starts Postgres if needed, creates a temporary database, runs migrations against it, executes the integration test, and drops the temporary database afterward.
