from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import ProjectRegistry
from app.main import create_app
from app.models import Project, Run, Task, TaskEvent, TaskStatus, utc_now
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


class WorktreeRunner:
    def execute(self, task: Task, run: Run, store: InMemoryStore, broker: EventBroker) -> None:
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


def make_context(tmp_path: Path) -> tuple[TestClient, TaskService, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_git_repo(project_root)

    project = Project(
        id="demo",
        name="Demo",
        path=str(project_root),
        default_branch="main",
    )
    store = InMemoryStore(projects=[project])
    broker = EventBroker()
    workspace_manager = WorkspaceManager(state_root=tmp_path / "state")
    service = TaskService(store=store, workspace_manager=workspace_manager, broker=broker)
    service.runner = InstantRunner()

    client = TestClient(create_app(service))
    return client, service, project_root


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

    projects_response = client.get("/projects")
    assert projects_response.status_code == 200
    assert projects_response.json()[0]["id"] == "demo"


def test_task_lifecycle_and_approval(tmp_path: Path) -> None:
    client, _, _ = make_context(tmp_path)

    task_response = client.post(
        "/tasks",
        json={
            "project_id": "demo",
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
    assert "PROJECT:" in detail["run"]["structured_prompt"]

    approval_response = client.post(f"/tasks/{task_id}/approval", json={"action": "approve"})
    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "completed"


def test_task_runs_in_worktree_and_applies_on_approval(tmp_path: Path) -> None:
    client, service, project_root = make_context(tmp_path)
    service.runner = WorktreeRunner()

    task_id = client.post(
        "/tasks",
        json={"project_id": "demo", "prompt": "Create a README"},
    ).json()["id"]

    detail = wait_for_status(client, task_id, "awaiting_approval")
    run_payload = detail["run"]
    assert run_payload["base_cwd"] == str(project_root)
    assert Path(run_payload["cwd"]).exists()
    assert not (project_root / "README.md").exists()
    assert (Path(run_payload["cwd"]) / "README.md").exists()

    approval_response = client.post(f"/tasks/{task_id}/approval", json={"action": "approve"})
    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "completed"
    assert (project_root / "README.md").exists()
    assert not Path(run_payload["cwd"]).exists()


def test_event_stream_includes_task_history(tmp_path: Path) -> None:
    client, service, _ = make_context(tmp_path)
    task_id = client.post(
        "/tasks",
        json={"project_id": "demo", "prompt": "Document the API"},
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


def test_project_registry_loads_project_context(tmp_path: Path) -> None:
    config_root = tmp_path / ".codeclaw"
    project_root = tmp_path / "registered-project"
    project_root.mkdir()
    project_meta_dir = config_root / "projects" / "demo"
    project_meta_dir.mkdir(parents=True)

    (config_root / "config.toml").write_text(
        """
[defaults]
sandbox = "workspace-write"
approval_required = true

[[projects]]
id = "demo"
name = "Demo"
path = "__PROJECT_ROOT__"
""".replace("__PROJECT_ROOT__", str(project_root)),
        encoding="utf-8",
    )
    (project_meta_dir / "config.toml").write_text(
        """
default_branch = "main"

[context]
summary = "Local project summary"
extra_constraints = ["Never edit generated files"]
""",
        encoding="utf-8",
    )
    (project_meta_dir / "instructions.md").write_text(
        "Use the internal build harness before changing APIs.",
        encoding="utf-8",
    )

    registry = ProjectRegistry.load(config_root)

    assert len(registry.projects) == 1
    project = registry.projects[0]
    assert project.id == "demo"
    assert project.default_branch == "main"
    assert project.context.summary == "Local project summary"
    assert project.context.extra_constraints == ["Never edit generated files"]
    assert project.context.instructions == "Use the internal build harness before changing APIs."
