# Codex Harness Boundary

This document defines the intended boundary between:

- the reusable Codex execution harness
- the CodeClaw product-specific application shell

The goal is to make the execution and review pipeline usable from other projects without requiring them to reuse CodeClaw's FastAPI, TOML layout, or SQL schema.

## Core Decision

CodeClaw should be treated as one consumer of a reusable Codex task runtime.

That means:

- the reusable unit is the Codex harness
- the non-reusable unit is the current app shell around it

## What Should Be Reusable

The reusable harness should own the workflow for:

- preparing an isolated workspace
- executing Codex against a target working directory
- emitting task lifecycle events
- capturing durable artifacts such as diff, stdout, and stderr
- handling approval, apply, and reject semantics
- maintaining a coherent task lifecycle state machine

This is the part another project should be able to embed or call.

## What Should Stay CodeClaw-Specific

The following concerns should remain adapters or product shell behavior:

- FastAPI routes
- request and response shapes chosen for this app
- TOML-backed project registration under `~/.codeclaw`
- SQLAlchemy persistence details and schema choices
- any future CodeClaw-specific UI behavior
- any future authentication or user/session model

Another project may want completely different interfaces for these concerns while still using the same Codex harness underneath.

## Target Layering

The intended architecture is:

1. harness/runtime layer
2. adapter layer
3. CodeClaw product layer

### Harness/Runtime Layer

This layer should be reusable across products.

Likely responsibilities:

- task lifecycle orchestration
- workspace execution coordination
- artifact capture
- approval/apply/reject behavior
- event contracts
- runner abstraction

This layer should not depend on FastAPI, TOML, or a particular persistence backend.

### Adapter Layer

This layer connects the harness to concrete infrastructure.

Examples:

- Codex CLI runner
- git worktree manager
- SQL-backed task store
- TOML-backed project catalog
- artifact persistence on local disk

Adapters can remain CodeClaw-owned while still being separate from the core runtime.

### CodeClaw Product Layer

This is the app-specific shell.

Examples:

- API endpoints
- project registration API behavior
- local configuration management conventions
- UI-facing models and flow decisions

## Boundary Rule

If another project would reasonably need the behavior even when it does not share CodeClaw's API or config model, the logic probably belongs in the reusable harness or in a reusable adapter.

If the behavior only exists because CodeClaw chose a specific product interface or storage convention, it should stay in the CodeClaw shell.

## Current Couplings To Reduce

Today, some components are still more product-shaped than reusable.

The main couplings to reduce over time are:

- `TaskService` mixes runtime orchestration with API-facing and project-registration concerns
- project registration is tied directly to the TOML-backed config model
- API models and internal runtime models overlap heavily
- workspace management and artifact persistence are bundled closely together

These are reasonable current tradeoffs, but they should be separated before attempting extraction.

## Likely Reusable Interfaces

The reusable harness will probably need a small set of stable interfaces such as:

- task store or task state sink
- runner
- workspace manager
- artifact sink or artifact manager
- event sink or event publisher
- project/workspace descriptor

The exact names can change, but the important point is that the harness should depend on interfaces, not on FastAPI, TOML, or SQLAlchemy directly.

## Non-Goal

The goal is not to make the entire CodeClaw backend reusable as-is.

The goal is to make the Codex execution and review pipeline reusable.

Another project should be able to:

- submit work to Codex
- observe progress
- review generated artifacts
- approve or reject the result

without adopting:

- CodeClaw's HTTP API
- CodeClaw's config layout
- CodeClaw's database schema

## Immediate Next Step

Before extracting code, keep documenting and refactoring toward the boundary inside this repository.

That means future implementation work should prefer:

- thinner FastAPI route handlers
- clearer separation between project catalog concerns and task execution concerns
- explicit interfaces around runner, store, workspace, and artifact behavior
- isolating product-specific policy from execution-runtime behavior
