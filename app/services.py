from __future__ import annotations

from app.api_models import ProjectRegistration, TaskCreate, TaskDetail
from app.harness import (
    ArtifactManager,
    CodexRunner,
    EventBroker,
    ExecutionTarget,
    PromptBuilder,
    RunnerProtocol,
    TargetContext,
    TargetExecutionSettings,
    TaskRuntime,
    TaskSnapshot,
    TaskSubmission,
    WorkspaceManager,
)
from app.models import Project, Task
from app.project_service import ProjectService
from app.store import Store


class TaskService:
    """Product-facing service that delegates task execution to the runtime layer."""

    def __init__(
        self,
        store: Store,
        workspace_manager: WorkspaceManager,
        broker: EventBroker,
        project_service: ProjectService | None = None,
    ) -> None:
        self.store = store
        self.workspace_manager = workspace_manager
        self.broker = broker
        self.project_service = project_service or ProjectService(
            store=store,
            workspace_manager=workspace_manager,
        )
        self.runtime = TaskRuntime(
            store=store,
            target_resolver=_ProjectTargetResolver(store),
            workspace_manager=workspace_manager,
            artifact_manager=ArtifactManager(getattr(workspace_manager, "state_root", None)),
            broker=broker,
            prompt_builder=PromptBuilder(),
            runner=CodexRunner(),
        )

    @property
    def runner(self) -> RunnerProtocol:
        return self.runtime.runner

    @runner.setter
    def runner(self, value: RunnerProtocol) -> None:
        self.runtime.runner = value

    def list_projects(self) -> list[Project]:
        """Return the configured projects that this instance can execute against."""
        return self.project_service.list_projects()

    def get_project(self, project_id: str) -> Project:
        """Return one registered project."""
        return self.project_service.get_project(project_id)

    def register_project(self, payload: ProjectRegistration) -> Project:
        """Register an existing local git repository as an available project."""
        return self.project_service.register_project(payload)

    def create_task(self, payload: TaskCreate) -> Task:
        return self.runtime.create_task(
            TaskSubmission(
                target_id=payload.project_id,
                prompt=payload.prompt,
                mode=payload.mode,
                constraints=list(payload.constraints),
                acceptance_criteria=list(payload.acceptance_criteria),
            )
        )

    def list_tasks(self) -> list[Task]:
        return self.runtime.list_tasks()

    def get_task_detail(self, task_id: str) -> TaskDetail:
        return self._build_task_detail(self.runtime.get_task_detail(task_id))

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

    @staticmethod
    def _build_task_detail(detail: TaskSnapshot) -> TaskDetail:
        return TaskDetail(
            task=detail.task,
            run=detail.run,
            recent_events=detail.recent_events,
        )


__all__ = ["EventBroker", "TaskService", "WorkspaceManager"]


class _ProjectTargetResolver:
    def __init__(self, store: Store) -> None:
        self.store = store

    def get_target(self, target_id: str) -> ExecutionTarget | None:
        project = self.store.get_project(target_id)
        if project is None:
            return None
        return ExecutionTarget(
            id=project.id,
            name=project.name,
            path=project.path,
            default_branch=project.default_branch,
            execution=TargetExecutionSettings(
                approval_required=project.execution.approval_required,
                auto_create_branch=project.execution.auto_create_branch,
                branch_prefix=project.execution.branch_prefix,
            ),
            context=TargetContext(
                summary=project.context.summary,
                extra_constraints=list(project.context.extra_constraints),
                instructions=project.context.instructions,
            ),
        )
