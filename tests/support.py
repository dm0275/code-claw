from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.harness import EventBroker, Run, RunnerResult, Task, TaskEvent


class InstantRunner:
    def execute(self, task: Task, run: Run, broker: EventBroker) -> RunnerResult:
        broker.publish(
            TaskEvent(
                task_id=task.id,
                type="log",
                message="runner executed",
            )
        )
        return RunnerResult(
            exit_code=0,
            summary="Instant runner completed",
            stdout=["runner executed"],
            files_modified=["app/main.py"],
        )


class WorktreeRunner:
    def execute(self, task: Task, run: Run, broker: EventBroker) -> RunnerResult:
        readme_path = Path(run.cwd) / "README.md"
        readme_path.write_text(
            "# Demo\n\nCreated from isolated worktree execution.\n",
            encoding="utf-8",
        )
        broker.publish(
            TaskEvent(
                task_id=task.id,
                type="log",
                message="runner executed in isolated worktree",
            )
        )
        return RunnerResult(
            exit_code=0,
            summary="Worktree runner completed",
            stdout=["runner executed in isolated worktree"],
            files_modified=["README.md"],
        )


class FailingRunner:
    def execute(self, task: Task, run: Run, broker: EventBroker) -> RunnerResult:
        raise RuntimeError("runner exploded")


class AnswerRunner:
    def execute(self, task: Task, run: Run, broker: EventBroker) -> RunnerResult:
        broker.publish(
            TaskEvent(
                task_id=task.id,
                type="log",
                message="answer runner returned a no-change response",
            )
        )
        return RunnerResult(
            exit_code=0,
            summary=(
                "You can sort a dictionary by value with "
                "`sorted(data.items(), key=lambda item: item[1])`."
            ),
            stdout=["answer runner completed without modifying the workspace"],
            files_modified=[],
        )


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
