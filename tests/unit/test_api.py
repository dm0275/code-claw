from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("CODECLAW_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.config import ProjectRegistry
from app.db import ApprovalRow, create_all_tables, init_db
from app.main import create_app
from app.models import ApprovalAction, Project, Run, Task, utc_now
from app.services import EventBroker, TaskService, WorkspaceManager
from app.sql_store import SqlStore
from app.store import InMemoryStore
from tests.support import (
    FailingRunner,
    InstantRunner,
    WorktreeRunner,
    init_git_repo,
    sse_event_payloads,
    wait_for_path_absence,
    wait_for_status,
)


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


def make_sql_context(tmp_path: Path) -> tuple[TestClient, TaskService, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_git_repo(project_root)

    database_path = tmp_path / "codeclaw.db"
    session_factory = create_all_tables(f"sqlite+pysqlite:///{database_path}")
    project = Project(
        id="demo",
        name="Demo",
        path=str(project_root),
        default_branch="main",
    )
    store = SqlStore(projects=[project], session_factory=session_factory)
    broker = EventBroker()
    workspace_manager = WorkspaceManager(state_root=tmp_path / "state")
    service = TaskService(store=store, workspace_manager=workspace_manager, broker=broker)
    service.runner = InstantRunner()

    client = TestClient(create_app(service))
    return client, service, project_root


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
    assert Path(run_payload["diff_path"]).exists()
    assert Path(run_payload["stdout_path"]).exists()
    assert Path(run_payload["stderr_path"]).exists()

    diff_response = client.get(f"/tasks/{task_id}/diff")
    assert diff_response.status_code == 200
    assert "README.md" in diff_response.text
    assert "Created from isolated worktree execution." in diff_response.text

    approval_response = client.post(f"/tasks/{task_id}/approval", json={"action": "approve"})
    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "completed"
    assert (project_root / "README.md").exists()
    assert not Path(run_payload["cwd"]).exists()


def test_task_reject_cleans_up_worktree_without_touching_base_repo(tmp_path: Path) -> None:
    client, service, project_root = make_context(tmp_path)
    service.runner = WorktreeRunner()

    task_id = client.post(
        "/tasks",
        json={"project_id": "demo", "prompt": "Create a README"},
    ).json()["id"]

    detail = wait_for_status(client, task_id, "awaiting_approval")
    run_payload = detail["run"]
    assert not (project_root / "README.md").exists()

    reject_response = client.post(f"/tasks/{task_id}/approval", json={"action": "reject"})
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"
    assert not (project_root / "README.md").exists()
    assert not Path(run_payload["cwd"]).exists()


def test_failed_runner_marks_task_failed_and_cleans_up_worktree(tmp_path: Path) -> None:
    client, service, _ = make_context(tmp_path)
    service.runner = FailingRunner()

    task_id = client.post(
        "/tasks",
        json={"project_id": "demo", "prompt": "Fail this task"},
    ).json()["id"]

    detail = wait_for_status(client, task_id, "failed")
    run_payload = detail["run"]
    assert detail["task"]["summary"] == "runner exploded"
    assert run_payload["exit_code"] == 1
    wait_for_path_absence(Path(run_payload["cwd"]))


def test_approval_conflict_when_base_repo_is_dirty(tmp_path: Path) -> None:
    client, service, project_root = make_context(tmp_path)
    service.runner = WorktreeRunner()

    task_id = client.post(
        "/tasks",
        json={"project_id": "demo", "prompt": "Create a README"},
    ).json()["id"]

    detail = wait_for_status(client, task_id, "awaiting_approval")
    run_payload = detail["run"]

    (project_root / "local.txt").write_text("dirty\n", encoding="utf-8")
    approval_response = client.post(f"/tasks/{task_id}/approval", json={"action": "approve"})

    assert approval_response.status_code == 409
    assert "uncommitted changes" in approval_response.json()["detail"]
    assert not (project_root / "README.md").exists()
    assert Path(run_payload["cwd"]).exists()


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

    event_payloads = sse_event_payloads(messages)
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


def test_sql_store_persists_tasks_runs_and_approvals(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_git_repo(project_root)

    database_path = tmp_path / "codeclaw.db"
    session_factory = create_all_tables(f"sqlite+pysqlite:///{database_path}")
    project = Project(id="demo", name="Demo", path=str(project_root), default_branch="main")

    store = SqlStore(projects=[project], session_factory=session_factory)
    task = Task(project_id="demo", prompt="Persist me")
    run = Run(task_id=task.id, cwd=str(project_root), structured_prompt="OBJECTIVE:\nPersist me")
    store.add_task(task)
    store.set_run(run)
    store.add_approval(task.id, action=ApprovalAction.APPROVE, created_at=utc_now())

    restarted_store = SqlStore(projects=[project], session_factory=session_factory)
    persisted_task = restarted_store.get_task(task.id)
    persisted_run = restarted_store.get_run(task.id)

    assert persisted_task is not None
    assert persisted_task.prompt == "Persist me"
    assert persisted_run is not None
    assert persisted_run.cwd == str(project_root)

    with session_factory() as session:
        approvals = session.query(ApprovalRow).filter(ApprovalRow.task_id == task.id).all()

    assert len(approvals) == 1
    assert approvals[0].action == "approve"


def test_sql_backed_service_reloads_task_history(tmp_path: Path) -> None:
    client, _, project_root = make_sql_context(tmp_path)

    task_response = client.post(
        "/tasks",
        json={"project_id": "demo", "prompt": "Persist through API"},
    )
    task_id = task_response.json()["id"]
    detail = wait_for_status(client, task_id, "awaiting_approval")

    database_path = tmp_path / "codeclaw.db"
    session_factory = init_db(f"sqlite+pysqlite:///{database_path}")
    project = Project(id="demo", name="Demo", path=str(project_root), default_branch="main")
    restarted_store = SqlStore(projects=[project], session_factory=session_factory)
    restarted_service = TaskService(
        store=restarted_store,
        workspace_manager=WorkspaceManager(state_root=tmp_path / "state"),
        broker=EventBroker(),
    )

    reloaded_detail = restarted_service.get_task_detail(task_id)
    assert reloaded_detail.task.prompt == "Persist through API"
    assert reloaded_detail.run is not None
    assert reloaded_detail.run.task_id == task_id
    assert detail["task"]["id"] == reloaded_detail.task.id
