from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict, List, Optional

from app.models import Project, Run, Task, TaskEvent


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
