from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Run, Task, TaskEvent, TaskStatus, utc_now
from app.services import EventBroker, TaskService, WorkspaceManager
from app.store import InMemoryStore


class InstantRunner:
    def execute(self, task: Task, run: Run, store: InMemoryStore, broker: EventBroker) -> None:
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


def make_context(tmp_path: Path) -> tuple[TestClient, TaskService, Path]:
    store = InMemoryStore()
    broker = EventBroker()
    service = TaskService(store=store, workspace_manager=WorkspaceManager(), broker=broker)
    service.runner = InstantRunner()

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    client = TestClient(create_app(service))
    return client, service, workspace_root


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


def test_healthcheck(tmp_path: Path) -> None:
    client, _, _ = make_context(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_task_lifecycle_and_approval(tmp_path: Path) -> None:
    client, _, workspace_root = make_context(tmp_path)

    workspace_response = client.post(
        "/workspaces",
        json={"name": "repo", "path": str(workspace_root), "branch": "main"},
    )
    assert workspace_response.status_code == 201
    workspace_id = workspace_response.json()["id"]

    task_response = client.post(
        "/tasks",
        json={
            "workspace_id": workspace_id,
            "prompt": "Add pagination",
            "constraints": ["Only change API files"],
            "acceptance_criteria": ["Tests pass"],
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    detail = wait_for_status(client, task_id, "awaiting_approval")
    assert detail["task"]["summary"] == "Instant runner completed"
    assert detail["task"]["files_modified"] == ["app/main.py"]
    assert detail["run"]["exit_code"] == 0
    assert "OBJECTIVE:" in detail["run"]["structured_prompt"]
    assert "ACCEPTANCE CRITERIA:" in detail["run"]["structured_prompt"]

    approval_response = client.post(f"/tasks/{task_id}/approval", json={"action": "approve"})
    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "completed"


def test_event_stream_includes_task_history(tmp_path: Path) -> None:
    client, service, workspace_root = make_context(tmp_path)

    workspace_id = client.post(
        "/workspaces",
        json={"name": "repo", "path": str(workspace_root)},
    ).json()["id"]
    task_id = client.post(
        "/tasks",
        json={"workspace_id": workspace_id, "prompt": "Document the API"},
    ).json()["id"]

    wait_for_status(client, task_id, "awaiting_approval")

    generator = service.stream_task_events(task_id)
    messages = [next(generator) for _ in range(4)]

    body = "".join(messages)
    assert "event: status" in body
    assert "Task created" in body
    assert "Task is running" in body

    event_payloads = []
    for message in messages:
        for line in message.splitlines():
            if line.startswith("data: "):
                event_payloads.append(json.loads(line.removeprefix("data: ")))

    assert any(item["message"] == "Task is awaiting approval" for item in event_payloads)
