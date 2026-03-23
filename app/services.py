from __future__ import annotations

import json
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Dict, Iterator

from fastapi import HTTPException, status

from app.models import (
    ApprovalAction,
    Run,
    Task,
    TaskCreate,
    TaskDetail,
    TaskEvent,
    TaskStatus,
    Workspace,
    WorkspaceCreate,
    utc_now,
)
from app.store import InMemoryStore


class EventBroker:
    def __init__(self) -> None:
        self._streams: Dict[str, list[Queue[TaskEvent]]] = {}

    def publish(self, event: TaskEvent) -> None:
        for queue in self._streams.get(event.task_id, []):
            queue.put(event)

    def subscribe(self, task_id: str) -> Iterator[TaskEvent]:
        queue: Queue[TaskEvent] = Queue()
        self._streams.setdefault(task_id, []).append(queue)
        try:
            while True:
                try:
                    yield queue.get(timeout=15)
                except Empty:
                    yield TaskEvent(task_id=task_id, type="heartbeat", message="waiting")
        finally:
            self._streams[task_id].remove(queue)
            if not self._streams[task_id]:
                self._streams.pop(task_id, None)


class PromptBuilder:
    @staticmethod
    def build(task: Task, workspace: Workspace) -> str:
        sections = [
            "OBJECTIVE:",
            task.prompt,
            "",
            "WORKSPACE:",
            f"- Name: {workspace.name}",
            f"- Path: {workspace.path}",
        ]
        if task.constraints:
            sections.extend(["", "CONSTRAINTS:"])
            sections.extend(f"- {item}" for item in task.constraints)
        if task.acceptance_criteria:
            sections.extend(["", "ACCEPTANCE CRITERIA:"])
            sections.extend(f"- {item}" for item in task.acceptance_criteria)
        sections.extend(
            [
                "",
                "OUTPUT:",
                "- Summary",
                "- List of files changed",
                "- Execution log",
            ]
        )
        return "\n".join(sections)


class WorkspaceManager:
    def prepare(self, workspace: Workspace) -> Path:
        root = workspace.root
        if not root.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workspace path does not exist: {root}",
            )
        return root


class CodexRunner:
    def execute(self, task: Task, run: Run, store: InMemoryStore, broker: EventBroker) -> None:
        messages = [
            "Preparing workspace sandbox",
            "Constructed structured prompt",
            "Launching Codex CLI adapter",
            "Collecting modified files and summary",
        ]
        for message in messages:
            time.sleep(0.2)
            run.stdout.append(message)
            broker.publish(store.add_event(TaskEvent(task_id=task.id, type="log", message=message)))

        run.status = TaskStatus.AWAITING_APPROVAL
        run.exit_code = 0
        run.completed_at = utc_now()
        store.set_run(run)

        task.status = TaskStatus.AWAITING_APPROVAL
        task.summary = "Execution completed. Awaiting approval before changes are applied."
        task.files_modified = ["app/main.py", "app/services.py"]
        task.updated_at = utc_now()
        store.update_task(task)
        broker.publish(
            store.add_event(
                TaskEvent(
                    task_id=task.id,
                    type="status",
                    message="Task is awaiting approval",
                )
            )
        )


class TaskService:
    def __init__(
        self,
        store: InMemoryStore,
        workspace_manager: WorkspaceManager,
        broker: EventBroker,
    ) -> None:
        self.store = store
        self.workspace_manager = workspace_manager
        self.broker = broker
        self.prompt_builder = PromptBuilder()
        self.runner = CodexRunner()

    def create_workspace(self, payload: WorkspaceCreate) -> Workspace:
        workspace = Workspace(**payload.model_dump())
        self.workspace_manager.prepare(workspace)
        return self.store.add_workspace(workspace)

    def list_workspaces(self) -> list[Workspace]:
        return self.store.list_workspaces()

    def create_task(self, payload: TaskCreate) -> Task:
        workspace = self.store.get_workspace(payload.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

        self.workspace_manager.prepare(workspace)
        task = Task(**payload.model_dump())
        self.store.add_task(task)
        self._publish(task.id, "status", "Task created")

        worker = Thread(target=self._run_task, args=(task.id,), daemon=True)
        worker.start()
        return task

    def _run_task(self, task_id: str) -> None:
        task = self._require_task(task_id)
        workspace = self._require_workspace(task.workspace_id)

        task.status = TaskStatus.RUNNING
        task.updated_at = utc_now()
        self.store.update_task(task)
        self._publish(task.id, "status", "Task is running")

        structured_prompt = self.prompt_builder.build(task, workspace)
        run = Run(
            task_id=task.id,
            cwd=workspace.path,
            structured_prompt=structured_prompt,
            status=TaskStatus.RUNNING,
        )
        self.store.set_run(run)
        self._publish(task.id, "prompt", structured_prompt)

        try:
            self.runner.execute(task, run, self.store, self.broker)
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

    def list_tasks(self) -> list[Task]:
        return self.store.list_tasks()

    def get_task_detail(self, task_id: str) -> TaskDetail:
        task = self._require_task(task_id)
        return TaskDetail(
            task=task,
            run=self.store.get_run(task_id),
            recent_events=self.store.list_events(task_id),
        )

    def approve_task(self, task_id: str, action: ApprovalAction) -> Task:
        task = self._require_task(task_id)
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task is not awaiting approval",
            )

        if action is ApprovalAction.APPROVE:
            task.status = TaskStatus.COMPLETED
            task.summary = "Approved. Changes can now be applied in the workspace pipeline."
            event_message = "Task approved"
        else:
            task.status = TaskStatus.REJECTED
            task.summary = "Rejected. No changes should be applied."
            event_message = "Task rejected"

        task.updated_at = utc_now()
        task.completed_at = utc_now()
        self.store.update_task(task)
        self._publish(task.id, "status", event_message)
        return task

    def stream_task_events(self, task_id: str) -> Iterator[str]:
        self._require_task(task_id)
        history = self.store.list_events(task_id)
        for event in history:
            yield self._format_sse(event)
        for event in self.broker.subscribe(task_id):
            yield self._format_sse(event)

    def _require_task(self, task_id: str) -> Task:
        task = self.store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task

    def _require_workspace(self, workspace_id: str) -> Workspace:
        workspace = self.store.get_workspace(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        return workspace

    def _publish(self, task_id: str, event_type: str, message: str) -> None:
        event = self.store.add_event(TaskEvent(task_id=task_id, type=event_type, message=message))
        self.broker.publish(event)

    @staticmethod
    def _format_sse(event: TaskEvent) -> str:
        payload = json.dumps(event.model_dump(mode="json"))
        return f"event: {event.type}\ndata: {payload}\n\n"
