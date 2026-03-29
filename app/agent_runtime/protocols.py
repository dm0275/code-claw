"""Protocols that define the reusable agent runtime extension points.

Applications embedding the agent runtime typically implement:
- `TargetResolverProtocol`
- optionally a custom `WorkspaceManagerProtocol`
- optionally a custom `RunnerProtocol`
"""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from app.agent_runtime.models import ExecutionTarget, RunnerResult
from app.agent_runtime.state import Run, Task, TaskEvent


class EventBrokerProtocol(Protocol):
    """Publish and subscribe to task-scoped events."""

    def publish(self, event: TaskEvent) -> None: ...

    def subscribe(self, task_id: str) -> Iterator[TaskEvent]: ...


class PromptBuilderProtocol(Protocol):
    """Build a runner prompt from task data plus a resolved execution target."""

    def build(self, task: Task, target: ExecutionTarget) -> str: ...


class WorkspaceManagerProtocol(Protocol):
    """Prepare and clean up a task workspace for one execution target."""

    def prepare(self, target: ExecutionTarget) -> object: ...

    def prepare_task_workspace(self, target: ExecutionTarget, task_id: str) -> Any: ...

    def apply_task_changes(self, workspace: Any) -> None: ...

    def cleanup_task_workspace(self, workspace: Any) -> None: ...


class ArtifactManagerProtocol(Protocol):
    """Persist durable artifacts for later review or retrieval."""

    def persist_task_artifacts(self, task_id: str, workspace: Any, run: Run) -> Run: ...


class TargetResolverProtocol(Protocol):
    """Resolve a caller-provided target id into an execution target."""

    def get_target(self, target_id: str) -> ExecutionTarget | None: ...


class RunnerProtocol(Protocol):
    """Execute one task run and return a generic agent-run result."""

    def execute(
        self,
        task: Task,
        run: Run,
        broker: EventBrokerProtocol,
    ) -> RunnerResult: ...
