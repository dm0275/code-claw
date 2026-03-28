from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Run, Task, TaskEvent


@dataclass(frozen=True)
class TargetContext:
    summary: str | None = None
    extra_constraints: list[str] = field(default_factory=list)
    instructions: str | None = None


@dataclass(frozen=True)
class TargetExecutionSettings:
    approval_required: bool = True
    auto_create_branch: bool = False
    branch_prefix: str | None = None


@dataclass(frozen=True)
class ExecutionTarget:
    id: str
    path: str
    name: str | None = None
    default_branch: str | None = None
    execution: TargetExecutionSettings = field(default_factory=TargetExecutionSettings)
    context: TargetContext = field(default_factory=TargetContext)


@dataclass(frozen=True)
class TaskSubmission:
    target_id: str
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
