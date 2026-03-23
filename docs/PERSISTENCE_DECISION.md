# Persistence Decision

This document records the current persistence direction for CodeClaw and the reasoning behind it.

## Decision

CodeClaw will use PostgreSQL for durable application state.

The project registry remains TOML-based under `~/.codeclaw/`, but runtime state should move into Postgres rather than MongoDB.

## Why PostgreSQL

The core backend data model is relational and state-machine oriented:

- projects
- tasks
- runs
- approvals
- task events
- artifact metadata

These records have strong relationships and consistency requirements. PostgreSQL fits that shape better than a document database.

### Main reasons

- Task lifecycle updates should be transactional.
- Runs and approvals naturally reference tasks.
- Query patterns are relational:
  - all tasks for a project
  - latest run for a task
  - tasks awaiting approval
  - failed tasks with run history
- Foreign keys and indexes will help keep the data model correct as the system grows.
- This system benefits from a clear execution ledger and auditable history.

## Why Not MongoDB Right Now

MongoDB is workable, but it is not the best fit for the current problem shape.

The main tradeoffs are:

- weaker relational guarantees
- more application-managed consistency
- more awkward query patterns for task/run/approval history
- higher risk of denormalized drift as the model evolves

MongoDB would make more sense if the primary stored objects were large, highly variable, unstructured agent documents. That is not the current architecture.

## Storage Split

The intended split is:

- PostgreSQL
  - tasks
  - runs
  - approvals
  - task event metadata
  - artifact metadata
- filesystem or object storage
  - raw logs
  - diff files
  - archived outputs

## Local Development

For local development, a pinned Postgres container is provided in [`compose.yaml`](../compose.yaml).

The image is intentionally pinned to a specific version instead of `latest` so local behavior stays reproducible.

## Follow-up Implementation Plan

1. Add a Postgres-backed persistence layer for tasks, runs, and approvals.
2. Keep the TOML project registry as-is.
3. Persist lifecycle state as the source of truth instead of in-memory storage.
4. Add migrations.
5. Add restart-safe tests around task history and approval state.
