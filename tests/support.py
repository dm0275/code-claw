from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.harness import EventBroker
from app.models import Run, Task, TaskEvent, TaskStatus, utc_now
from app.store import Store


class InstantRunner:
    def execute(self, task: Task, run: Run, store: Store, broker: EventBroker) -> None:
        run.stdout.append("runner executed")
        run.status = TaskStatus.AWAITING_APPROVAL
        run.exit_code = 0
        run.completed_at = utc_now()
        store.set_run(run)

        task.status = TaskStatus.AWAITING_APPROVAL
        task.summary = "Instant runner completed"
        task.files_modified = ["app/main.py"]
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


class WorktreeRunner:
    def execute(self, task: Task, run: Run, store: Store, broker: EventBroker) -> None:
        readme_path = Path(run.cwd) / "README.md"
        readme_path.write_text(
            "# Demo\n\nCreated from isolated worktree execution.\n",
            encoding="utf-8",
        )

        run.stdout.append("runner executed in isolated worktree")
        run.status = TaskStatus.AWAITING_APPROVAL
        run.exit_code = 0
        run.completed_at = utc_now()
        store.set_run(run)

        task.status = TaskStatus.AWAITING_APPROVAL
        task.summary = "Worktree runner completed"
        task.files_modified = ["README.md"]
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


class FailingRunner:
    def execute(self, task: Task, run: Run, store: Store, broker: EventBroker) -> None:
        raise RuntimeError("runner exploded")


def init_git_repo(project_root: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=project_root, check=True)
    subprocess.run(["git", "config", "user.name", "CodeClaw Tests"], cwd=project_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "codeclaw-tests@example.com"],
        cwd=project_root,
        check=True,
    )
    (project_root / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=project_root, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=project_root, check=True)


def wait_for_status(
    client: TestClient,
    task_id: str,
    expected_status: str,
    timeout_seconds: float = 1.0,
) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/tasks/{task_id}")
        payload = response.json()
        if payload["task"]["status"] == expected_status:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"Task {task_id} did not reach status {expected_status}")


def wait_for_path_absence(path: Path, timeout_seconds: float = 1.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"Path {path} still exists")


def sse_event_payloads(messages: list[str]) -> list[dict]:
    payloads: list[dict] = []
    for message in messages:
        for line in message.splitlines():
            if line.startswith("data: "):
                payloads.append(json.loads(line.removeprefix("data: ")))
    return payloads
