from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

from app.api_models import ProjectRegistration
from app.config import ProjectRegistryManager
from app.harness import WorkspaceManager
from app.models import Project
from app.store import Store


class ProjectService:
    """Own project catalog and registration behavior for the app shell."""

    def __init__(
        self,
        store: Store,
        workspace_manager: WorkspaceManager,
        project_registry_manager: ProjectRegistryManager | None = None,
    ) -> None:
        self.store = store
        self.workspace_manager = workspace_manager
        self.project_registry_manager = project_registry_manager or ProjectRegistryManager()

    def list_projects(self) -> list[Project]:
        return self.store.list_projects()

    def get_project(self, project_id: str) -> Project:
        project = self.store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    def register_project(self, payload: ProjectRegistration) -> Project:
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
