from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from app.models import Project, ProjectContext, ProjectExecution


def default_config_root() -> Path:
    """Return the root directory that stores local CodeClaw configuration."""
    configured = os.environ.get("CODECLAW_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".codeclaw"


class ProjectRegistry:
    """Load and expose the set of projects the user has explicitly registered."""

    def __init__(self, projects: list[Project]) -> None:
        self.projects = projects

    @classmethod
    def load(cls, root: Path | None = None) -> "ProjectRegistry":
        """Load global project registrations plus per-project metadata from TOML."""
        config_root = (root or default_config_root()).expanduser().resolve()
        registry_path = config_root / "config.toml"
        if not registry_path.exists():
            return cls(projects=[])

        data = _read_toml(registry_path)
        defaults = data.get("defaults", {})
        project_entries = data.get("projects", [])
        projects = [
            _build_project(config_root, defaults, item)
            for item in project_entries
            if bool(item.get("enabled", True))
        ]
        return cls(projects=projects)


def _build_project(config_root: Path, defaults: dict[str, Any], item: dict[str, Any]) -> Project:
    """Merge registry defaults with per-project config and instructions."""
    project_id = str(item["id"])
    project_dir = Path(item.get("project_dir", config_root / "projects" / project_id)).expanduser()

    project_config_path = project_dir / "config.toml"
    project_config = _read_toml(project_config_path) if project_config_path.exists() else {}
    instructions_path = project_dir / "instructions.md"
    instructions = (
        instructions_path.read_text(encoding="utf-8").strip()
        if instructions_path.exists()
        else None
    )

    execution_defaults = {
        "sandbox": defaults.get("sandbox", "workspace-write"),
        "approval_required": defaults.get("approval_required", True),
        "auto_create_branch": defaults.get("auto_create_branch", False),
        "branch_prefix": defaults.get("branch_prefix"),
        "extra_writable_dirs": defaults.get("extra_writable_dirs", []),
    }
    execution_config = {**execution_defaults, **project_config.get("execution", {})}

    context_config = project_config.get("context", {})
    context = ProjectContext(
        summary=context_config.get("summary"),
        extra_constraints=list(context_config.get("extra_constraints", [])),
        instructions=instructions,
    )

    return Project(
        id=project_id,
        name=str(item.get("name", project_id)),
        path=str(item["path"]),
        enabled=bool(item.get("enabled", True)),
        default_branch=project_config.get("default_branch") or item.get("default_branch"),
        project_dir=str(project_dir),
        execution=ProjectExecution(**execution_config),
        context=context,
    )


def _read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file into a plain dict."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}
