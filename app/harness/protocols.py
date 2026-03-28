from __future__ import annotations

from typing import Any, Iterator, Protocol

from app.harness.models import RunnerResult
from app.models import Project, Run, Task, TaskEvent


class EventBrokerProtocol(Protocol):
    def publish(self, event: TaskEvent) -> None: ...

    def subscribe(self, task_id: str) -> Iterator[TaskEvent]: ...


class PromptBuilderProtocol(Protocol):
    def build(self, task: Task, project: Project) -> str: ...


class WorkspaceManagerProtocol(Protocol):
    def prepare(self, project: Project) -> object: ...

    def prepare_task_workspace(self, project: Project, task_id: str) -> Any: ...

    def apply_task_changes(self, workspace: Any) -> None: ...

    def cleanup_task_workspace(self, workspace: Any) -> None: ...


class ArtifactManagerProtocol(Protocol):
    def persist_task_artifacts(self, task_id: str, workspace: Any, run: Run) -> Run: ...


class RunnerProtocol(Protocol):
    """Execute one task run and return a generic agent-run result."""

    def execute(
        self,
        task: Task,
        run: Run,
        broker: EventBrokerProtocol,
    ) -> RunnerResult: ...
