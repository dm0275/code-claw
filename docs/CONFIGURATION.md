# Configuration

CodeClaw only runs tasks against predefined projects registered in a managed TOML config.

Current state:

- the backend reads projects from TOML
- the app/API can now register existing local git repositories into that TOML-backed registry
- direct TOML editing is still supported, but it is no longer required for the basic add-project flow

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

The registry still lives at `~/.codeclaw/config.toml`.

You can populate it either:

- through the app/API via `POST /projects`
- manually by editing the TOML file

Manual example:

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
- The app/API registration flow writes the same TOML layout that the loader already understands.
