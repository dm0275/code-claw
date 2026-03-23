from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from tempfile import NamedTemporaryFile
from threading import Thread
from typing import Any, Dict, Iterator, TextIO

from fastapi import HTTPException, status

from app.models import (
    ApprovalAction,
    Project,
    Run,
    Task,
    TaskCreate,
    TaskDetail,
    TaskEvent,
    TaskStatus,
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
    def build(task: Task, project: Project) -> str:
        sections = [
            "OBJECTIVE:",
            task.prompt,
            "",
            "PROJECT:",
            f"- Name: {project.name}",
            f"- Path: {project.path}",
        ]
        if project.context.summary:
            sections.extend(["", "PROJECT CONTEXT:", project.context.summary])
        if task.constraints:
            sections.extend(["", "CONSTRAINTS:"])
            sections.extend(f"- {item}" for item in task.constraints)
        if project.context.extra_constraints:
            if "CONSTRAINTS:" not in sections:
                sections.extend(["", "CONSTRAINTS:"])
            sections.extend(f"- {item}" for item in project.context.extra_constraints)
        if task.acceptance_criteria:
            sections.extend(["", "ACCEPTANCE CRITERIA:"])
            sections.extend(f"- {item}" for item in task.acceptance_criteria)
        if project.context.instructions:
            sections.extend(["", "ADDITIONAL INSTRUCTIONS:", project.context.instructions])
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
    def prepare(self, project: Project) -> Path:
        root = project.root
        if not root.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workspace path does not exist: {root}",
            )
        return root


@dataclass
class CodexCliResult:
    exit_code: int
    summary: str
    stdout: list[str]
    stderr: list[str]
    files_modified: list[str]


class CodexRunner:
    def __init__(self, binary: str = "codex") -> None:
        self.binary = binary

    def execute(self, task: Task, run: Run, store: InMemoryStore, broker: EventBroker) -> None:
        cwd = Path(run.cwd)
        self._publish_log(task.id, "Launching Codex CLI", store, broker)
        result = self._run_codex(cwd, run.structured_prompt, task.id, store, broker)

        run.stdout = result.stdout
        run.stderr = result.stderr
        run.exit_code = result.exit_code
        run.completed_at = utc_now()
        run.status = TaskStatus.AWAITING_APPROVAL if result.exit_code == 0 else TaskStatus.FAILED
        store.set_run(run)

        task.status = TaskStatus.AWAITING_APPROVAL if result.exit_code == 0 else TaskStatus.FAILED
        task.summary = result.summary
        task.files_modified = result.files_modified
        task.updated_at = utc_now()
        task.completed_at = utc_now() if result.exit_code != 0 else None
        store.update_task(task)

        if result.exit_code == 0:
            self._publish_status(task.id, "Task is awaiting approval", store, broker)
        else:
            self._publish_status(task.id, "Task failed", store, broker)

    def _run_codex(
        self,
        cwd: Path,
        prompt: str,
        task_id: str,
        store: InMemoryStore,
        broker: EventBroker,
    ) -> CodexCliResult:
        with NamedTemporaryFile(mode="w+", encoding="utf-8", suffix=".txt") as output_file:
            command = [
                self.binary,
                "exec",
                "--json",
                "--skip-git-repo-check",
                "--sandbox",
                "workspace-write",
                "--cd",
                str(cwd),
                "--output-last-message",
                output_file.name,
                prompt,
            ]
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            stdout_thread = Thread(
                target=self._consume_stream,
                args=(process.stdout, stdout_lines, task_id, "log", store, broker),
                daemon=True,
            )
            stderr_thread = Thread(
                target=self._consume_stream,
                args=(process.stderr, stderr_lines, task_id, "error", store, broker),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            exit_code = process.wait()
            stdout_thread.join()
            stderr_thread.join()

            output_file.seek(0)
            summary = output_file.read().strip()
            if not summary:
                summary = (
                    "Execution completed. Awaiting approval before changes are applied."
                    if exit_code == 0
                    else "Codex execution failed."
                )

        files_modified = self._collect_changed_files(cwd) if exit_code == 0 else []
        return CodexCliResult(
            exit_code=exit_code,
            summary=summary,
            stdout=stdout_lines,
            stderr=stderr_lines,
            files_modified=files_modified,
        )

    def _consume_stream(
        self,
        stream: TextIO | None,
        sink: list[str],
        task_id: str,
        event_type: str,
        store: InMemoryStore,
        broker: EventBroker,
    ) -> None:
        if stream is None:
            return
        try:
            for raw_line in stream:
                line = raw_line.rstrip()
                if not line:
                    continue
                sink.append(line)
                message = self._format_stream_message(line)
                event = store.add_event(
                    TaskEvent(task_id=task_id, type=event_type, message=message)
                )
                broker.publish(event)
        finally:
            stream.close()

    def _format_stream_message(self, line: str) -> str:
        try:
            payload: Dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return line

        event_type = payload.get("type")
        if event_type == "agent_reasoning":
            return str(payload.get("text", "agent reasoning"))
        if event_type == "agent_message":
            message = payload.get("message")
            if isinstance(message, dict):
                return str(message.get("content", line))
        if event_type == "exec_command_begin":
            command = payload.get("command", [])
            if isinstance(command, list):
                return f"Running command: {' '.join(str(item) for item in command)}"
        if event_type == "exec_command_output_delta":
            return str(payload.get("chunk", line))
        if event_type == "task_complete":
            return str(payload.get("last_agent_message", "Task complete"))
        return line

    def _collect_changed_files(self, cwd: Path) -> list[str]:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []

        files: list[str] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            files.append(line[3:] if len(line) > 3 else line)
        return sorted(set(files))

    def _publish_log(
        self,
        task_id: str,
        message: str,
        store: InMemoryStore,
        broker: EventBroker,
    ) -> None:
        event = store.add_event(TaskEvent(task_id=task_id, type="log", message=message))
        broker.publish(event)

    def _publish_status(
        self,
        task_id: str,
        message: str,
        store: InMemoryStore,
        broker: EventBroker,
    ) -> None:
        event = store.add_event(TaskEvent(task_id=task_id, type="status", message=message))
        broker.publish(event)


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

    def list_projects(self) -> list[Project]:
        return self.store.list_projects()

    def create_task(self, payload: TaskCreate) -> Task:
        project = self.store.get_project(payload.project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        self.workspace_manager.prepare(project)
        task = Task(**payload.model_dump())
        self.store.add_task(task)
        self._publish(task.id, "status", "Task created")

        worker = Thread(target=self._run_task, args=(task.id,), daemon=True)
        worker.start()
        return task

    def _run_task(self, task_id: str) -> None:
        task = self._require_task(task_id)
        project = self._require_project(task.project_id)

        task.status = TaskStatus.RUNNING
        task.updated_at = utc_now()
        self.store.update_task(task)
        self._publish(task.id, "status", "Task is running")

        structured_prompt = self.prompt_builder.build(task, project)
        run = Run(
            task_id=task.id,
            cwd=project.path,
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

    def _require_project(self, project_id: str) -> Project:
        project = self.store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    def _publish(self, task_id: str, event_type: str, message: str) -> None:
        event = self.store.add_event(TaskEvent(task_id=task_id, type=event_type, message=message))
        self.broker.publish(event)

    @staticmethod
    def _format_sse(event: TaskEvent) -> str:
        payload = json.dumps(event.model_dump(mode="json"))
        return f"event: {event.type}\ndata: {payload}\n\n"
