from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Run, Task, TaskEvent


@dataclass(frozen=True)
class TaskSubmission:
    project_id: str
    prompt: str
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TaskSnapshot:
    task: Task
    run: Run | None = None
    recent_events: list[TaskEvent] = field(default_factory=list)


@dataclass(frozen=True)
class RunnerResult:
    exit_code: int
    summary: str
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
