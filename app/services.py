from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

from app.config import ProjectRegistryManager
from app.models import Project, ProjectRegistration, Task, TaskCreate, TaskDetail
from app.runtime import CodexRunner, EventBroker, PromptBuilder, TaskRuntime, WorkspaceManager
from app.store import Store


class TaskService:
    """Product-facing service that delegates task execution to the runtime layer."""

    def __init__(
        self,
        store: Store,
        workspace_manager: WorkspaceManager,
        broker: EventBroker,
        project_registry_manager: ProjectRegistryManager | None = None,
    ) -> None:
        self.store = store
        self.workspace_manager = workspace_manager
        self.broker = broker
        self.project_registry_manager = project_registry_manager or ProjectRegistryManager()
        self.runtime = TaskRuntime(
            store=store,
            workspace_manager=workspace_manager,
            broker=broker,
            prompt_builder=PromptBuilder(),
            runner=CodexRunner(),
        )

    @property
    def runner(self) -> CodexRunner:
        return self.runtime.runner

    @runner.setter
    def runner(self, value: CodexRunner) -> None:
        self.runtime.runner = value

    def list_projects(self) -> list[Project]:
        """Return the configured projects that this instance can execute against."""
        return self.store.list_projects()

    def get_project(self, project_id: str) -> Project:
        """Return one registered project."""
        return self._require_project(project_id)

    def register_project(self, payload: ProjectRegistration) -> Project:
        """Register an existing local git repository as an available project."""
        candidate = Project(
            id=payload.id,
            name=payload.name,
            path=str(Path(payload.path).expanduser().resolve()),
            default_branch=payload.default_branch,
            execution=payload.execution,
            context=payload.context,
        )
        self.workspace_manager.prepare(candidate)

        try:
            project = self.project_registry_manager.register_project(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        self.store.register_project(project)
        return project

    def create_task(self, payload: TaskCreate) -> Task:
        return self.runtime.create_task(payload)

    def list_tasks(self) -> list[Task]:
        return self.runtime.list_tasks()

    def get_task_detail(self, task_id: str) -> TaskDetail:
        return self.runtime.get_task_detail(task_id)

    def approve_task(self, task_id: str, action) -> Task:
        return self.runtime.approve_task(task_id, action)

    def stream_task_events(self, task_id: str):
        return self.runtime.stream_task_events(task_id)

    def get_task_diff(self, task_id: str) -> str:
        return self.runtime.get_task_diff(task_id)

    def get_task_stdout(self, task_id: str) -> str:
        return self.runtime.get_task_stdout(task_id)

    def get_task_stderr(self, task_id: str) -> str:
        return self.runtime.get_task_stderr(task_id)

    def _require_project(self, project_id: str) -> Project:
        project = self.store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project


__all__ = ["EventBroker", "TaskService", "WorkspaceManager"]
