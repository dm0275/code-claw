# Configuration

CodeClaw only runs tasks against predefined projects registered in a managed TOML config.

Current state:

- the backend already reads projects from TOML
- today, users still create and edit that TOML manually
- the next planned product task is adding project registration through the app/API

The planned direction for project onboarding is documented in [PROJECT_REGISTRATION_PLAN.md](/Users/dmancilla/git/code-claw/docs/PROJECT_REGISTRATION_PLAN.md).

## Layout

```text
~/.codeclaw/
├── config.toml
└── projects/
    └── <project-id>/
        ├── config.toml
        └── instructions.md
```

## Global registry

Today, create `~/.codeclaw/config.toml` manually:

```toml
[defaults]
sandbox = "workspace-write"
approval_required = true
auto_create_branch = false

[[projects]]
id = "code-claw"
name = "CodeClaw"
path = "/Users/dmancilla/git/code-claw"
```

## Per-project metadata

Optional file: `~/.codeclaw/projects/code-claw/config.toml`

```toml
default_branch = "main"

[execution]
sandbox = "workspace-write"
approval_required = true
auto_create_branch = true
branch_prefix = "codeclaw/task"
extra_writable_dirs = []

[context]
summary = "FastAPI backend for orchestrating Codex CLI tasks."
extra_constraints = [
  "Do not edit generated files unless explicitly requested.",
  "Prefer backend changes before UI work.",
]
```

Optional file: `~/.codeclaw/projects/code-claw/instructions.md`

Use this for long-form local-only guidance that should affect Codex prompts but should not be committed into the repository.

## Current behavior

- Only projects declared in `~/.codeclaw/config.toml` are available to the API.
- Tasks must target a `project_id`.
- Per-project `config.toml` and `instructions.md` are merged into prompt construction.
- If the global config file does not exist, the API starts with zero available projects.
- Manual TOML editing is temporary product behavior, not the intended long-term onboarding flow.
