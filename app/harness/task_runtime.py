"""Core orchestration runtime for the reusable harness package.

`TaskRuntime` is the main entry point for consumers that want the full task
lifecycle:
- resolve a target id
- prepare a workspace
- execute a runner
- persist artifacts
- optionally wait for approval or auto-complete
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock, Thread
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from app.harness.artifacts import ArtifactManager
from app.harness.models import RunnerResult, TaskSnapshot, TaskSubmission
from app.harness.prompt_builder import PromptBuilder
from app.harness.protocols import (
    ArtifactManagerProtocol,
    EventBrokerProtocol,
    PromptBuilderProtocol,
    RunnerProtocol,
    TargetResolverProtocol,
    WorkspaceManagerProtocol,
)
from app.harness.runners import CodexRunner
from app.harness.workspace import TaskWorkspace, WorkspaceManager
from app.models import ApprovalAction, Run, Task, TaskEvent, TaskStatus, utc_now
from app.store import Store


class TaskRuntime:
    """Own the execution, review, and approval lifecycle for tasks.

    Example:
    ```python
    runtime = TaskRuntime(
        store=store,
        target_resolver=resolver,
        workspace_manager=WorkspaceManager(),
        broker=EventBroker(),
    )
    runtime.create_task(TaskSubmission(target_id="demo", prompt="Update docs"))
    ```
    """

    def __init__(
        self,
        store: Store,
        target_resolver: TargetResolverProtocol,
        workspace_manager: WorkspaceManagerProtocol,
        broker: EventBrokerProtocol,
        artifact_manager: ArtifactManagerProtocol | None = None,
        prompt_builder: PromptBuilderProtocol | None = None,
        runner: RunnerProtocol | None = None,
    ) -> None:
        self.store = store
        self.target_resolver = target_resolver
        self.workspace_manager = workspace_manager
        if artifact_manager is None:
            if not isinstance(workspace_manager, WorkspaceManager):
                raise TypeError(
                    "artifact_manager is required when workspace_manager is not WorkspaceManager"
                )
            artifact_manager = ArtifactManager(workspace_manager.state_root)
        self.artifact_manager = artifact_manager
        self.broker = broker
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.runner = runner or CodexRunner()
        self.task_workspaces: dict[str, TaskWorkspace] = {}
        self._artifact_locks: dict[str, Lock] = {}

    def create_task(self, submission: TaskSubmission) -> Task:
        """Create a task record and start execution in a background thread."""
        target = self._require_target(submission.target_id)

        self.workspace_manager.prepare(target)
        task = Task(
            project_id=submission.target_id,
            prompt=submission.prompt,
            constraints=list(submission.constraints),
            acceptance_criteria=list(submission.acceptance_criteria),
        )
        self.store.add_task(task)
        self._publish(task.id, "status", "Task created")

        worker = Thread(target=self._run_task, args=(task.id,), daemon=True)
        worker.start()
        return task

    def list_tasks(self) -> list[Task]:
        """Return all known tasks from the backing store."""
        return self.store.list_tasks()

    def get_task_detail(self, task_id: str) -> TaskSnapshot:
        """Return the task, associated run, and recent task events."""
        task = self._require_task(task_id)
        self._ensure_review_artifacts(task_id, task)
        return TaskSnapshot(
            task=task,
            run=self.store.get_run(task_id),
            recent_events=self.store.list_events(task_id),
        )

    def approve_task(self, task_id: str, action: ApprovalAction) -> Task:
        """Approve or reject a completed task and handle any resulting workspace actions."""
        task = self._require_task(task_id)
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task is not awaiting approval",
            )

        if action is ApprovalAction.APPROVE:
            self._ensure_approval_persistence_ready()
            self._apply_task_changes(task_id)
            task.status = TaskStatus.COMPLETED
            task.summary = "Approved. Changes can now be applied in the workspace pipeline."
            event_message = "Task approved"
        else:
            task.status = TaskStatus.REJECTED
            task.summary = "Rejected. No changes should be applied."
            event_message = "Task rejected"

        task.updated_at = utc_now()
        task.completed_at = utc_now()
        try:
            self.store.finalize_approval(task, action, task.completed_at)
        except (OperationalError, ProgrammingError, DBAPIError) as exc:
            raise self._translate_approval_persistence_error(exc) from exc
        self._publish(task.id, "status", event_message)
        self._cleanup_task_workspace(task_id)
        return task

    def stream_task_events(self, task_id: str) -> Iterator[str]:
        """Yield existing and live events as server-sent event payloads."""
        self._require_task(task_id)
        history = self.store.list_events(task_id)
        for event in history:
            yield self._format_sse(event)
        for event in self.broker.subscribe(task_id):
            yield self._format_sse(event)

    def get_task_diff(self, task_id: str) -> str:
        """Return the stored unified diff for a task."""
        return self._get_task_artifact(task_id, "diff_path", "Task diff not found")

    def get_task_stdout(self, task_id: str) -> str:
        """Return the stored stdout log for a task."""
        return self._get_task_artifact(task_id, "stdout_path", "Task stdout log not found")

    def get_task_stderr(self, task_id: str) -> str:
        """Return the stored stderr log for a task."""
        return self._get_task_artifact(task_id, "stderr_path", "Task stderr log not found")

    def _run_task(self, task_id: str) -> None:
        """Execute one task end to end inside the configured runtime policy."""
        task = self._require_task(task_id)
        target = self._require_target(task.project_id)
        approval_required = target.execution.approval_required

        task.status = TaskStatus.RUNNING
        task.updated_at = utc_now()
        self.store.update_task(task)
        self._publish(task.id, "status", "Task is running")

        structured_prompt = self.prompt_builder.build(task, target)
        task_workspace = self.workspace_manager.prepare_task_workspace(target, task.id)
        self.task_workspaces[task.id] = task_workspace
        run = Run(
            task_id=task.id,
            cwd=str(task_workspace.worktree_root),
            base_cwd=str(task_workspace.base_root),
            target_branch=task_workspace.branch_name,
            structured_prompt=structured_prompt,
            status=TaskStatus.RUNNING,
        )
        self.store.set_run(run)
        self._publish(task.id, "prompt", structured_prompt)

        try:
            result = self.runner.execute(task, run, self.broker)
            review_required = self._requires_review(result, approval_required)
            self._apply_runner_result(task, run, result, approval_required=review_required)
            if result.exit_code == 0:
                if result.files_modified:
                    self._persist_review_artifacts(task.id, task, task_workspace, run)
                if review_required:
                    return
                self._complete_without_approval(
                    task,
                    run,
                    task_workspace,
                    apply_changes=bool(result.files_modified),
                )
                return
        except Exception as exc:
            run.status = TaskStatus.FAILED
            run.exit_code = 1
            run.stderr.append(str(exc))
            run.completed_at = utc_now()
            self.store.set_run(run)

            task.status = TaskStatus.FAILED
            task.summary = str(exc)
            task.updated_at = utc_now()
            task.completed_at = utc_now()
            self.store.update_task(task)
            self._publish(task.id, "error", f"Task failed: {exc}")
            self._cleanup_task_workspace(task.id)

    def _require_task(self, task_id: str) -> Task:
        task = self.store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task

    def _require_target(self, target_id: str):
        """Resolve a target id or raise a 404-style runtime error."""
        target = self.target_resolver.get_target(target_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return target

    def _publish(self, task_id: str, event_type: str, message: str) -> None:
        event = self.store.add_event(TaskEvent(task_id=task_id, type=event_type, message=message))
        self.broker.publish(event)

    def _apply_runner_result(
        self,
        task: Task,
        run: Run,
        result: RunnerResult,
        *,
        approval_required: bool,
    ) -> None:
        """Translate a normalized runner result into persisted task and run state."""
        success_status = self._success_status(approval_required)
        run.stdout = list(result.stdout)
        run.stderr = list(result.stderr)
        run.exit_code = result.exit_code
        run.completed_at = utc_now()
        run.status = success_status if result.exit_code == 0 else TaskStatus.FAILED
        self.store.set_run(run)

        task.status = success_status if result.exit_code == 0 else TaskStatus.FAILED
        task.summary = result.summary
        task.files_modified = list(result.files_modified)
        task.updated_at = utc_now()
        task.completed_at = utc_now() if result.exit_code != 0 or not approval_required else None
        self.store.update_task(task)

        if result.exit_code == 0:
            self._publish(
                task.id,
                "status",
                "Task is awaiting approval" if approval_required else "Task completed",
            )
        else:
            self._publish(task.id, "status", "Task failed")

    def _complete_without_approval(
        self,
        task: Task,
        run: Run,
        workspace: TaskWorkspace,
        *,
        apply_changes: bool,
    ) -> None:
        """Apply and finalize a successful task when approval is disabled."""
        if apply_changes:
            self.workspace_manager.apply_task_changes(workspace)
        task.status = TaskStatus.COMPLETED
        task.updated_at = utc_now()
        task.completed_at = utc_now()
        self.store.update_task(task)

        run.status = TaskStatus.COMPLETED
        run.completed_at = task.completed_at
        self.store.set_run(run)

        self._publish(task.id, "status", "Task completed")
        self._cleanup_task_workspace(task.id)

    def _apply_task_changes(self, task_id: str) -> None:
        workspace = self.task_workspaces.get(task_id)
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task workspace is no longer available",
            )
        self.workspace_manager.apply_task_changes(workspace)

    def _ensure_approval_persistence_ready(self) -> None:
        try:
            self.store.ensure_approval_persistence_ready()
        except (OperationalError, ProgrammingError, DBAPIError) as exc:
            raise self._translate_approval_persistence_error(exc) from exc

    def _cleanup_task_workspace(self, task_id: str) -> None:
        workspace = self.task_workspaces.pop(task_id, None)
        if workspace is None:
            return
        self.workspace_manager.cleanup_task_workspace(workspace)
        self._artifact_locks.pop(task_id, None)

    def _ensure_review_artifacts(self, task_id: str, task: Task) -> None:
        """Persist artifacts on demand before callers fetch task detail or logs."""
        if task.status not in (TaskStatus.AWAITING_APPROVAL, TaskStatus.COMPLETED):
            return

        run = self.store.get_run(task_id)
        workspace = self.task_workspaces.get(task_id)
        if run is None or workspace is None or run.diff_path:
            return

        self._persist_review_artifacts(task_id, task, workspace, run)

    def _get_task_artifact(self, task_id: str, field_name: str, missing_detail: str) -> str:
        """Read one persisted artifact and translate missing files into HTTP errors."""
        task = self._require_task(task_id)
        self._ensure_review_artifacts(task_id, task)
        run = self.store.get_run(task_id)
        path_value = getattr(run, field_name, None) if run is not None else None
        if not path_value:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing_detail)

        artifact_path = Path(path_value)
        if not artifact_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing_detail)
        return artifact_path.read_text(encoding="utf-8")

    def _persist_review_artifacts(
        self,
        task_id: str,
        task: Task,
        workspace: TaskWorkspace,
        run: Run,
    ) -> None:
        """Persist artifacts once per task, even if multiple callers race to fetch them."""
        lock = self._artifact_locks.setdefault(task_id, Lock())
        with lock:
            latest_run = self.store.get_run(task_id)
            if latest_run is not None and latest_run.diff_path:
                run.diff_path = latest_run.diff_path
                run.stdout_path = latest_run.stdout_path
                run.stderr_path = latest_run.stderr_path
                return

            if task.status is not TaskStatus.AWAITING_APPROVAL:
                return

            self.artifact_manager.persist_task_artifacts(task_id, workspace, run)
            self.store.set_run(run)

    @staticmethod
    def _format_sse(event: TaskEvent) -> str:
        """Serialize one task event into a server-sent event payload."""
        payload = json.dumps(event.model_dump(mode="json"))
        return f"event: {event.type}\ndata: {payload}\n\n"

    @staticmethod
    def _translate_approval_persistence_error(exc: Exception) -> HTTPException:
        """Map storage-layer approval failures into user-facing HTTP errors."""
        message = str(exc).lower()
        indicators = [
            "no such table",
            "undefinedtable",
            "does not exist",
            "has no column named",
            "no column named",
            "undefined column",
            "unknown column",
            "relation",
        ]
        if any(token in message for token in indicators):
            return HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Approval persistence failed because the runtime database schema is out "
                    "of date. Run `make db-migrate` and retry the approval."
                ),
            )
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Approval persistence failed unexpectedly.",
        )

    @staticmethod
    def _success_status(approval_required: bool) -> TaskStatus:
        """Return the steady-state success status for the current approval policy."""
        return TaskStatus.AWAITING_APPROVAL if approval_required else TaskStatus.COMPLETED

    @staticmethod
    def _requires_review(result: RunnerResult, approval_required: bool) -> bool:
        """Require review only when policy requires it and the run produced changes."""
        return approval_required and bool(result.files_modified)
