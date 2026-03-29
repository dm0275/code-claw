"""Harness-local storage protocol.

Host applications can satisfy this protocol with their own persistence layer
without importing the harness from an app-specific store module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.harness.state import ApprovalAction, Run, Task, TaskEvent


class RuntimeStoreProtocol(Protocol):
    def add_task(self, task: Task) -> Task: ...

    def update_task(self, task: Task) -> Task: ...

    def list_tasks(self) -> list[Task]: ...

    def get_task(self, task_id: str) -> Task | None: ...

    def set_run(self, run: Run) -> Run: ...

    def get_run(self, task_id: str) -> Run | None: ...

    def ensure_approval_persistence_ready(self) -> None: ...

    def finalize_approval(
        self,
        task: Task,
        action: ApprovalAction,
        created_at: datetime,
    ) -> Task: ...

    def add_event(self, event: TaskEvent) -> TaskEvent: ...

    def list_events(self, task_id: str) -> list[TaskEvent]: ...
