from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from tempfile import NamedTemporaryFile
from threading import Lock, Thread
from typing import Any, Dict, Iterator, TextIO

from fastapi import HTTPException, status
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

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
from app.store import Store


class EventBroker:
    """Fan out task events to any active SSE subscribers."""

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
        """Build the structured prompt sent to Codex for a single task run."""
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
    """Prepare isolated git worktrees and apply approved task diffs safely."""

    def __init__(self, state_root: Path | None = None) -> None:
        self.state_root = state_root or Path.home() / ".codeclaw" / "state"

    def prepare(self, project: Project) -> Path:
        """Validate that the configured project path exists and is a git repo."""
        root = project.root
        if not root.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workspace path does not exist: {root}",
            )
        git_check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if git_check.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Project path is not a git repository: {root}",
            )
        return root

    def prepare_task_workspace(self, project: Project, task_id: str) -> "TaskWorkspace":
        """Create a per-task git worktree so execution never touches the base checkout."""
        root = self.prepare(project)
        ref = self._resolve_base_ref(project, root)
        worktree_root = self.state_root / "worktrees" / project.id / task_id
        worktree_root.parent.mkdir(parents=True, exist_ok=True)
        if worktree_root.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_root)],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )

        branch_name: str | None = None
        command = ["git", "worktree", "add"]
        if project.execution.auto_create_branch:
            branch_name = self._branch_name(project, task_id)
            command.extend(["-b", branch_name])
        else:
            command.append("--detach")
        command.extend([str(worktree_root), ref])
        result = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Failed to create worktree"
            raise RuntimeError(message)

        return TaskWorkspace(
            base_root=root,
            worktree_root=worktree_root,
            ref=ref,
            branch_name=branch_name,
        )

    def apply_task_changes(self, workspace: "TaskWorkspace") -> None:
        """Apply the approved worktree diff back onto the base checkout."""
        if self._has_changes(workspace.base_root):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Base project has uncommitted changes; cannot apply task diff safely",
            )

        patch = self._build_task_patch(workspace)
        if patch:
            apply_result = subprocess.run(
                ["git", "apply", "--index", "--whitespace=nowarn", "-"],
                cwd=str(workspace.base_root),
                input=patch,
                capture_output=True,
                check=False,
            )
            if apply_result.returncode != 0:
                stderr = apply_result.stderr.decode("utf-8", errors="replace").strip()
                detail = stderr or "Failed to apply task diff"
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Patch conflict while applying task diff to the base project. "
                        f"{detail}"
                    ),
                )

    def persist_task_artifacts(self, task_id: str, workspace: "TaskWorkspace", run: Run) -> Run:
        """Write task logs and the staged patch to durable artifact files."""
        artifact_dir = self.state_root / "artifacts" / task_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        stdout_path = artifact_dir / "stdout.jsonl"
        stderr_path = artifact_dir / "stderr.jsonl"
        diff_path = artifact_dir / "diff.patch"

        stdout_contents = "\n".join(run.stdout) + ("\n" if run.stdout else "")
        stderr_contents = "\n".join(run.stderr) + ("\n" if run.stderr else "")
        stdout_path.write_text(stdout_contents, encoding="utf-8")
        stderr_path.write_text(stderr_contents, encoding="utf-8")
        diff_path.write_bytes(self._build_task_patch(workspace))

        run.stdout_path = str(stdout_path)
        run.stderr_path = str(stderr_path)
        run.diff_path = str(diff_path)
        return run

    def cleanup_task_workspace(self, workspace: "TaskWorkspace") -> None:
        """Remove the task worktree and its temporary branch if one was created."""
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(workspace.worktree_root)],
            cwd=str(workspace.base_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if workspace.branch_name:
            subprocess.run(
                ["git", "branch", "-D", workspace.branch_name],
                cwd=str(workspace.base_root),
                capture_output=True,
                text=True,
                check=False,
            )

    @staticmethod
    def _resolve_base_ref(project: Project, root: Path) -> str:
        if project.default_branch:
            return project.default_branch

        branch = subprocess.run(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if branch.returncode == 0:
            return branch.stdout.strip()
        return "HEAD"

    @staticmethod
    def _branch_name(project: Project, task_id: str) -> str:
        prefix = project.execution.branch_prefix or f"codeclaw/{project.id}"
        return f"{prefix}/{task_id[:8]}"

    @staticmethod
    def _has_changes(root: Path) -> bool:
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(status_result.stdout.strip())

    @staticmethod
    def _build_task_patch(workspace: "TaskWorkspace") -> bytes:
        stage_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(workspace.worktree_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if stage_result.returncode != 0:
            raise RuntimeError("Failed to stage task changes before capturing artifacts")

        diff = subprocess.run(
            ["git", "diff", "--cached", "--binary", "HEAD"],
            cwd=str(workspace.worktree_root),
            capture_output=True,
            text=False,
            check=False,
        )
        if diff.returncode != 0:
            raise RuntimeError("Failed to compute task diff")
        return diff.stdout


@dataclass
class TaskWorkspace:
    base_root: Path
    worktree_root: Path
    ref: str
    branch_name: str | None = None


@dataclass
class CodexCliResult:
    exit_code: int
    summary: str
    stdout: list[str]
    stderr: list[str]
    files_modified: list[str]


class CodexRunner:
    """Run Codex non-interactively and translate its output into task artifacts."""

    def __init__(self, binary: str = "codex") -> None:
        self.binary = binary

    def execute(self, task: Task, run: Run, store: Store, broker: EventBroker) -> None:
        """Execute Codex for a task and update run/task state from the result."""
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
        store: Store,
        broker: EventBroker,
    ) -> CodexCliResult:
        """Invoke `codex exec --json` and capture both streamed logs and final output."""
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
        store: Store,
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
        store: Store,
        broker: EventBroker,
    ) -> None:
        event = store.add_event(TaskEvent(task_id=task_id, type="log", message=message))
        broker.publish(event)

    def _publish_status(
        self,
        task_id: str,
        message: str,
        store: Store,
        broker: EventBroker,
    ) -> None:
        event = store.add_event(TaskEvent(task_id=task_id, type="status", message=message))
        broker.publish(event)


class TaskService:
    """Own the task lifecycle from creation through approval or rejection."""

    def __init__(
        self,
        store: Store,
        workspace_manager: WorkspaceManager,
        broker: EventBroker,
    ) -> None:
        self.store = store
        self.workspace_manager = workspace_manager
        self.broker = broker
        self.prompt_builder = PromptBuilder()
        self.runner = CodexRunner()
        self.task_workspaces: dict[str, TaskWorkspace] = {}
        self._artifact_locks: dict[str, Lock] = {}

    def list_projects(self) -> list[Project]:
        """Return the configured projects that this instance can execute against."""
        return self.store.list_projects()

    def create_task(self, payload: TaskCreate) -> Task:
        """Create a task record and start execution in a background thread."""
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
        task_workspace = self.workspace_manager.prepare_task_workspace(project, task.id)
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
            self.runner.execute(task, run, self.store, self.broker)
            if run.status is TaskStatus.AWAITING_APPROVAL:
                self._persist_review_artifacts(task.id, task, task_workspace, run)
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

    def list_tasks(self) -> list[Task]:
        return self.store.list_tasks()

    def get_task_detail(self, task_id: str) -> TaskDetail:
        """Return the task, associated run, and recent task events."""
        task = self._require_task(task_id)
        self._ensure_review_artifacts(task_id, task)
        return TaskDetail(
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
        if task.status is not TaskStatus.AWAITING_APPROVAL:
            return

        run = self.store.get_run(task_id)
        workspace = self.task_workspaces.get(task_id)
        if run is None or workspace is None or run.diff_path:
            return

        self._persist_review_artifacts(task_id, task, workspace, run)

    def _get_task_artifact(self, task_id: str, field_name: str, missing_detail: str) -> str:
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

            self.workspace_manager.persist_task_artifacts(task_id, workspace, run)
            self.store.set_run(run)

    @staticmethod
    def _format_sse(event: TaskEvent) -> str:
        payload = json.dumps(event.model_dump(mode="json"))
        return f"event: {event.type}\ndata: {payload}\n\n"

    @staticmethod
    def _translate_approval_persistence_error(exc: Exception) -> HTTPException:
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
