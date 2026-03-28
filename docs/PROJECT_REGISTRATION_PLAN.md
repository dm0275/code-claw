# Project Registration Plan

This document captures the current product direction for adding projects to CodeClaw.

## Decision

CodeClaw should support two distinct capabilities:

1. local project registration
2. repository cloning/import

These are intentionally separate.

## Why They Are Separate

Registering an existing local repository is a configuration and validation problem.

Cloning a repository is a source-acquisition problem with additional concerns:

- destination path selection
- SSH vs HTTPS authentication
- private repository credentials
- existing-directory conflicts
- default branch detection
- submodules
- Git LFS
- clone failures and retries
- trust and validation of remote URLs

Bundling both into one initial flow would make the first usable project-onboarding experience larger and less reliable than necessary.

## Current Product Direction

The next implementation task is local project registration only.

That means the product should let a user add an existing local git repository without manually editing `~/.codeclaw/config.toml`.

Cloning/import remains a possible future capability, but it is not part of the first project-onboarding implementation.

## Scope For The Next Task

The first project-registration flow should allow a user to:

- provide a project name
- provide or confirm a project id
- choose a local path
- optionally set the default branch
- optionally configure execution defaults such as approval requirement or branch prefix
- save the project into the managed CodeClaw registry

Backend validation should reject:

- missing paths
- non-git directories
- duplicate project ids
- duplicate project paths after normalization

## Expected Persistence Model

The registration flow should write the same config shape the backend already understands:

- `~/.codeclaw/config.toml`
- `~/.codeclaw/projects/<project-id>/config.toml`
- optionally `~/.codeclaw/projects/<project-id>/instructions.md`

This keeps the new UI/API path aligned with the existing config loader instead of introducing a second project registry format.

## Suggested API Direction

Start with backend endpoints for registration and management of local projects:

- `POST /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- optionally `DELETE /projects/{project_id}`

`POST /projects` should register an existing local repository, not clone one.

## Future Clone/Import Option

If clone/import is implemented later, it should be a separate action, not overloaded into local registration.

Examples:

- `POST /projects/import`
- `POST /projects/clone`

That keeps the local-registration path simple and keeps clone-specific failures and credential handling isolated.
