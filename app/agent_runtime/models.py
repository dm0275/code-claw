"""Public data models used by the reusable agent runtime.

These dataclasses define the runtime-facing contract so callers do not need to
depend on a host application's project-registration model just to execute a task.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agent_runtime.state import Run, Task, TaskEvent, TaskMode


@dataclass(frozen=True)
class TargetContext:
    """Optional descriptive context that helps shape the runner prompt."""

    summary: str | None = None
    extra_constraints: list[str] = field(default_factory=list)
    instructions: str | None = None


@dataclass(frozen=True)
class TargetExecutionSettings:
    """Execution policy attached to one harness target.

    Example:
    ```python
    TargetExecutionSettings(
        approval_required=False,
        auto_create_branch=True,
        branch_prefix="feature/my-app",
    )
    ```
    """

    approval_required: bool = True
    auto_create_branch: bool = False
    branch_prefix: str | None = None


@dataclass(frozen=True)
class ExecutionTarget:
    """A harness-native execution target.

    `path` is optional so callers can run response-only tasks without binding
    the harness to an existing local workspace.
    """

    id: str
    path: str | None = None
    name: str | None = None
    default_branch: str | None = None
    execution: TargetExecutionSettings = field(default_factory=TargetExecutionSettings)
    context: TargetContext = field(default_factory=TargetContext)


@dataclass(frozen=True)
class TaskSubmission:
    """A request to execute one task against a resolved target.

    `target_id` is intentionally just an identifier. The runtime asks a target
    resolver to map that id into an `ExecutionTarget` at execution time.
    """

    target_id: str
    prompt: str
    mode: TaskMode = TaskMode.CHANGE
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TaskSnapshot:
    """Read model returned from the runtime for task detail views."""

    task: Task
    run: Run | None = None
    recent_events: list[TaskEvent] = field(default_factory=list)


@dataclass(frozen=True)
class RunnerResult:
    """Normalized result returned by any harness runner implementation.

    This abstracts over Codex-specific output so future runners such as Claude
    can plug into the same runtime contract.
    """

    exit_code: int
    summary: str
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
