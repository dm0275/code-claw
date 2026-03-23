from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.config import ProjectRegistry
from app.db import make_session_factory
from app.models import ApprovalRequest, Project, Task, TaskCreate, TaskDetail
from app.services import EventBroker, TaskService, WorkspaceManager
from app.sql_store import SqlStore


def build_service() -> TaskService:
    """Build the default service graph from the user-managed project registry."""
    registry = ProjectRegistry.load()
    session_factory = make_session_factory()
    store = SqlStore(projects=registry.projects, session_factory=session_factory)
    broker = EventBroker()
    return TaskService(store=store, workspace_manager=WorkspaceManager(), broker=broker)


def create_app(task_service: TaskService | None = None) -> FastAPI:
    """Create the FastAPI app and optionally inject a test-specific service."""
    service = task_service or build_service()
    app = FastAPI(title="CodeClaw API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/projects", response_model=list[Project])
    def list_projects() -> list[Project]:
        return service.list_projects()

    @app.get("/tasks", response_model=list[Task])
    def list_tasks() -> list[Task]:
        return service.list_tasks()

    @app.post("/tasks", response_model=Task, status_code=201)
    def create_task(payload: TaskCreate) -> Task:
        return service.create_task(payload)

    @app.get("/tasks/{task_id}", response_model=TaskDetail)
    def get_task(task_id: str) -> TaskDetail:
        return service.get_task_detail(task_id)

    @app.post("/tasks/{task_id}/approval", response_model=Task)
    def approve_task(task_id: str, payload: ApprovalRequest) -> Task:
        return service.approve_task(task_id, payload.action)

    @app.get("/tasks/{task_id}/events")
    def stream_task_events(task_id: str) -> StreamingResponse:
        return StreamingResponse(
            service.stream_task_events(task_id),
            media_type="text/event-stream",
        )

    return app


app = create_app()
