# Configuration

CodeClaw only runs tasks against predefined projects registered in a user-managed TOML config.

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

Create `~/.codeclaw/config.toml`:

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
