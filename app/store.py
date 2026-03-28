from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
from typing import Deque, Dict, List, Optional, Protocol

from app.models import ApprovalAction, Project, Run, Task, TaskEvent


class Store(Protocol):
    """Common storage interface for runtime state used by the task service."""

    def list_projects(self) -> List[Project]: ...

    def get_project(self, project_id: str) -> Optional[Project]: ...

    def register_project(self, project: Project) -> Project: ...

    def add_task(self, task: Task) -> Task: ...

    def update_task(self, task: Task) -> Task: ...

    def list_tasks(self) -> List[Task]: ...

    def get_task(self, task_id: str) -> Optional[Task]: ...

    def set_run(self, run: Run) -> Run: ...

    def get_run(self, task_id: str) -> Optional[Run]: ...

    def ensure_approval_persistence_ready(self) -> None: ...

    def finalize_approval(
        self,
        task: Task,
        action: ApprovalAction,
        created_at: datetime,
    ) -> Task: ...

    def add_approval(self, task_id: str, action: ApprovalAction, created_at: datetime) -> None: ...

    def add_event(self, event: TaskEvent) -> TaskEvent: ...

    def list_events(self, task_id: str) -> List[TaskEvent]: ...


class InMemoryStore:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self._lock = Lock()
        self.projects: Dict[str, Project] = {project.id: project for project in projects or []}
        self.tasks: Dict[str, Task] = {}
        self.runs_by_task: Dict[str, Run] = {}
        self.events_by_task: Dict[str, Deque[TaskEvent]] = defaultdict(lambda: deque(maxlen=200))

    def list_projects(self) -> List[Project]:
        with self._lock:
            return list(self.projects.values())

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._lock:
            return self.projects.get(project_id)

    def register_project(self, project: Project) -> Project:
        with self._lock:
            self.projects[project.id] = project
            return project

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

    def ensure_approval_persistence_ready(self) -> None:
        return None

    def finalize_approval(
        self,
        task: Task,
        action: ApprovalAction,
        created_at: datetime,
    ) -> Task:
        del action, created_at
        with self._lock:
            self.tasks[task.id] = task
            return task

    def add_approval(
        self,
        task_id: str,
        action: ApprovalAction,
        created_at: datetime,
    ) -> None:
        del task_id, action, created_at

    def add_event(self, event: TaskEvent) -> TaskEvent:
        with self._lock:
            self.events_by_task[event.task_id].append(event)
            return event

    def list_events(self, task_id: str) -> List[TaskEvent]:
        with self._lock:
            return list(self.events_by_task[task_id])
