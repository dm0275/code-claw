from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict, List, Optional

from app.models import Run, Task, TaskEvent, Workspace


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.workspaces: Dict[str, Workspace] = {}
        self.tasks: Dict[str, Task] = {}
        self.runs_by_task: Dict[str, Run] = {}
        self.events_by_task: Dict[str, Deque[TaskEvent]] = defaultdict(lambda: deque(maxlen=200))

    def add_workspace(self, workspace: Workspace) -> Workspace:
        with self._lock:
            self.workspaces[workspace.id] = workspace
            return workspace

    def list_workspaces(self) -> List[Workspace]:
        with self._lock:
            return list(self.workspaces.values())

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        with self._lock:
            return self.workspaces.get(workspace_id)

    def add_task(self, task: Task) -> Task:
        with self._lock:
            self.tasks[task.id] = task
            return task

    def update_task(self, task: Task) -> Task:
        with self._lock:
            self.tasks[task.id] = task
            return task

    def list_tasks(self) -> List[Task]:
        with self._lock:
            return sorted(self.tasks.values(), key=lambda item: item.created_at, reverse=True)

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self.tasks.get(task_id)

    def set_run(self, run: Run) -> Run:
        with self._lock:
            self.runs_by_task[run.task_id] = run
            return run

    def get_run(self, task_id: str) -> Optional[Run]:
        with self._lock:
            return self.runs_by_task.get(task_id)

    def add_event(self, event: TaskEvent) -> TaskEvent:
        with self._lock:
            self.events_by_task[event.task_id].append(event)
            return event

    def list_events(self, task_id: str) -> List[TaskEvent]:
        with self._lock:
            return list(self.events_by_task[task_id])
