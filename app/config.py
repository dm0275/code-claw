from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from app.models import Project, ProjectContext, ProjectExecution, ProjectRegistration


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


class ProjectRegistryManager:
    """Persist project registrations in the on-disk config format the loader expects."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_config_root()).expanduser().resolve()

    def register_project(self, payload: ProjectRegistration) -> Project:
        registry = ProjectRegistry.load(self.root)
        normalized_path = Path(payload.path).expanduser().resolve()

        if any(project.id == payload.id for project in registry.projects):
            raise ValueError(f"Project id already exists: {payload.id}")
        if any(
            Path(project.path).expanduser().resolve() == normalized_path
            for project in registry.projects
        ):
            raise ValueError(f"Project path already exists: {normalized_path}")

        registry_path = self.root / "config.toml"
        registry_data = _read_toml(registry_path) if registry_path.exists() else {}
        defaults = registry_data.get("defaults", {})
        project_entries = list(registry_data.get("projects", []))
        project_entries.append(
            {
                "id": payload.id,
                "name": payload.name,
                "path": str(normalized_path),
                "enabled": True,
            }
        )

        self.root.mkdir(parents=True, exist_ok=True)
        _write_registry_toml(registry_path, defaults, project_entries)

        project_dir = self.root / "projects" / payload.id
        project_dir.mkdir(parents=True, exist_ok=True)
        _write_project_config_toml(project_dir / "config.toml", payload)
        _write_project_instructions(project_dir / "instructions.md", payload.context.instructions)

        persisted = ProjectRegistry.load(self.root)
        for project in persisted.projects:
            if project.id == payload.id:
                return project
        raise RuntimeError(f"Registered project could not be reloaded: {payload.id}")


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


def _write_registry_toml(
    path: Path,
    defaults: dict[str, Any],
    projects: list[dict[str, Any]],
) -> None:
    lines: list[str] = []
    if defaults:
        lines.append("[defaults]")
        for key, value in defaults.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")

    for project in projects:
        lines.append("[[projects]]")
        for key in ("id", "name", "path", "enabled", "default_branch", "project_dir"):
            if key in project and project[key] is not None:
                lines.append(f"{key} = {_toml_value(project[key])}")
        lines.append("")

    contents = "\n".join(lines).rstrip() + "\n"
    path.write_text(contents, encoding="utf-8")


def _write_project_config_toml(path: Path, payload: ProjectRegistration) -> None:
    lines: list[str] = []
    if payload.default_branch:
        lines.append(f"default_branch = {_toml_value(payload.default_branch)}")
        lines.append("")

    lines.append("[execution]")
    lines.append(f"sandbox = {_toml_value(payload.execution.sandbox)}")
    lines.append(f"approval_required = {_toml_value(payload.execution.approval_required)}")
    lines.append(f"auto_create_branch = {_toml_value(payload.execution.auto_create_branch)}")
    if payload.execution.branch_prefix is not None:
        lines.append(f"branch_prefix = {_toml_value(payload.execution.branch_prefix)}")
    lines.append(f"extra_writable_dirs = {_toml_value(payload.execution.extra_writable_dirs)}")
    lines.append("")

    lines.append("[context]")
    if payload.context.summary is not None:
        lines.append(f"summary = {_toml_value(payload.context.summary)}")
    lines.append(f"extra_constraints = {_toml_value(payload.context.extra_constraints)}")
    lines.append("")

    contents = "\n".join(lines).rstrip() + "\n"
    path.write_text(contents, encoding="utf-8")


def _write_project_instructions(path: Path, instructions: str | None) -> None:
    if instructions and instructions.strip():
        path.write_text(instructions.strip() + "\n", encoding="utf-8")
        return
    if path.exists():
        path.unlink()


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML value: {value!r}")
