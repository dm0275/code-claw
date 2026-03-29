from __future__ import annotations

import time
from pathlib import Path
from threading import Thread

import pytest
from fastapi import HTTPException

from app.harness import (
    ArtifactManager,
    EventBroker,
    ExecutionTarget,
    InPlaceWorkspaceManager,
    NoWorkspaceManager,
    PromptBuilder,
    TargetContext,
    TargetExecutionSettings,
    TaskRuntime,
    TaskSubmission,
    WorkspaceManager,
)
from app.models import ApprovalAction, Task, TaskEvent, TaskMode, TaskStatus
from app.store import InMemoryStore
from tests.support import AnswerRunner, WorktreeRunner, init_git_repo


class StaticTargetResolver:
    def __init__(self, *targets: ExecutionTarget) -> None:
        self._targets = {target.id: target for target in targets}

    def get_target(self, target_id: str) -> ExecutionTarget | None:
        return self._targets.get(target_id)


def wait_for_task_status(
    runtime: TaskRuntime,
    task_id: str,
    expected_status: TaskStatus,
    timeout_seconds: float = 1.0,
):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        snapshot = runtime.get_task_detail(task_id)
        if snapshot.task.status == expected_status:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"Task {task_id} did not reach status {expected_status}")


def make_target(
    project_root: Path,
    *,
    approval_required: bool = True,
    auto_create_branch: bool = False,
    branch_prefix: str | None = None,
) -> ExecutionTarget:
    return ExecutionTarget(
        id="demo",
        name="Demo",
        path=str(project_root),
        default_branch="main",
        execution=TargetExecutionSettings(
            approval_required=approval_required,
            auto_create_branch=auto_create_branch,
            branch_prefix=branch_prefix,
        ),
        context=TargetContext(
            summary="Demo repository for harness tests.",
            extra_constraints=["Do not change CI"],
            instructions="Prefer the smallest valid change.",
        ),
    )


def test_prompt_builder_includes_target_context_and_task_details(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    task = Task(
        project_id=target.id,
        prompt="Update the README",
        constraints=["Only touch docs"],
        acceptance_criteria=["README explains setup"],
    )

    prompt = PromptBuilder.build(task, target)

    assert "OBJECTIVE:" in prompt
    assert "PROJECT CONTEXT:" in prompt
    assert "Demo repository for harness tests." in prompt
    assert "- Only touch docs" in prompt
    assert "- Do not change CI" in prompt
    assert "ACCEPTANCE CRITERIA:" in prompt
    assert "ADDITIONAL INSTRUCTIONS:" in prompt
    assert f"- Path: {target.path}" in prompt


def test_prompt_builder_omits_file_change_output_for_response_mode(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    task = Task(
        project_id=target.id,
        prompt="Who is the first president of the United States?",
        mode=TaskMode.RESPONSE,
    )

    prompt = PromptBuilder.build(task, target)

    assert "TASK MODE:" in prompt
    assert "Response only. Do not modify files in the workspace." in prompt
    assert "- List of files changed" not in prompt


def test_prompt_builder_marks_target_without_workspace(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    target = ExecutionTarget(
        id=target.id,
        name=target.name,
        path=None,
        default_branch=target.default_branch,
        execution=target.execution,
        context=target.context,
    )
    task = Task(
        project_id=target.id,
        prompt="Who was the first president of the United States?",
        mode=TaskMode.RESPONSE,
    )

    prompt = PromptBuilder.build(task, target)

    assert "- Workspace: none" in prompt
    assert "- Path:" not in prompt


def test_event_broker_removes_subscriber_after_close() -> None:
    broker = EventBroker()
    stream = broker.subscribe("task-1")
    delivered: list[TaskEvent] = []

    def consume_one() -> None:
        delivered.append(next(stream))

    worker = Thread(target=consume_one)
    worker.start()
    time.sleep(0.05)

    broker.publish(TaskEvent(task_id="task-1", type="log", message="hello"))
    worker.join(timeout=1)

    assert delivered[0].message == "hello"
    assert "task-1" in broker._streams

    stream.close()

    assert "task-1" not in broker._streams


def test_task_runtime_requires_artifact_manager_for_in_place_workspace() -> None:
    runtime_store = InMemoryStore()
    target = ExecutionTarget(id="demo", path=".")

    with pytest.raises(TypeError, match="artifact_manager is required"):
        TaskRuntime(
            store=runtime_store,
            target_resolver=StaticTargetResolver(target),
            workspace_manager=InPlaceWorkspaceManager(),
            broker=EventBroker(),
        )


def test_task_runtime_create_task_raises_not_found_for_missing_target() -> None:
    runtime = TaskRuntime(
        store=InMemoryStore(),
        target_resolver=StaticTargetResolver(),
        workspace_manager=WorkspaceManager(),
        broker=EventBroker(),
    )

    with pytest.raises(HTTPException, match="Project not found") as exc:
        runtime.create_task(TaskSubmission(target_id="missing", prompt="Update docs"))

    assert exc.value.status_code == 404


def test_task_runtime_rejects_change_mode_without_workspace_path() -> None:
    target = ExecutionTarget(id="demo", path=None)
    runtime = TaskRuntime(
        store=InMemoryStore(),
        target_resolver=StaticTargetResolver(target),
        workspace_manager=NoWorkspaceManager(),
        artifact_manager=ArtifactManager(),
        broker=EventBroker(),
        runner=AnswerRunner(),
    )

    with pytest.raises(HTTPException, match="require an execution workspace path") as exc:
        runtime.create_task(TaskSubmission(target_id=target.id, prompt="Update docs"))

    assert exc.value.status_code == 400


def test_task_runtime_completes_answer_only_task_against_dirty_base_repo(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_git_repo(project_root)
    (project_root / "LOCAL_NOTES.txt").write_text("dirty checkout\n", encoding="utf-8")

    target = make_target(project_root, approval_required=True)
    runtime = TaskRuntime(
        store=InMemoryStore(),
        target_resolver=StaticTargetResolver(target),
        workspace_manager=WorkspaceManager(state_root=tmp_path / "state"),
        broker=EventBroker(),
        runner=AnswerRunner(),
    )

    task = runtime.create_task(
        TaskSubmission(
            target_id=target.id,
            prompt="How do you sort a dictionary by value?",
            mode=TaskMode.RESPONSE,
        )
    )
    snapshot = wait_for_task_status(runtime, task.id, TaskStatus.COMPLETED)

    assert "sorted(data.items()" in (snapshot.task.summary or "")
    assert snapshot.task.files_modified == []
    assert snapshot.run is not None
    assert snapshot.run.exit_code == 0
    assert snapshot.run.diff_path is None
    assert (project_root / "LOCAL_NOTES.txt").exists()
    assert task.id not in runtime.task_workspaces


def test_task_runtime_completes_response_mode_without_workspace_path(tmp_path: Path) -> None:
    target = ExecutionTarget(
        id="demo",
        name="No Workspace",
        path=None,
        execution=TargetExecutionSettings(approval_required=True),
    )
    state_root = tmp_path / "state"
    runtime = TaskRuntime(
        store=InMemoryStore(),
        target_resolver=StaticTargetResolver(target),
        workspace_manager=NoWorkspaceManager(state_root=state_root),
        artifact_manager=ArtifactManager(state_root),
        broker=EventBroker(),
        runner=AnswerRunner(),
    )

    task = runtime.create_task(
        TaskSubmission(
            target_id=target.id,
            prompt="Who was the first president of the United States?",
            mode=TaskMode.RESPONSE,
        )
    )
    snapshot = wait_for_task_status(runtime, task.id, TaskStatus.COMPLETED)

    assert snapshot.task.mode is TaskMode.RESPONSE
    assert snapshot.task.files_modified == []
    assert snapshot.run is not None
    assert snapshot.run.diff_path is None
    assert snapshot.run.cwd.endswith(task.id)
    assert task.id not in runtime.task_workspaces


def test_task_runtime_fails_response_mode_when_runner_modifies_files(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_git_repo(project_root)

    target = make_target(project_root, approval_required=True)
    runtime = TaskRuntime(
        store=InMemoryStore(),
        target_resolver=StaticTargetResolver(target),
        workspace_manager=WorkspaceManager(state_root=tmp_path / "state"),
        broker=EventBroker(),
        runner=WorktreeRunner(),
    )

    task = runtime.create_task(
        TaskSubmission(target_id=target.id, prompt="Answer directly", mode=TaskMode.RESPONSE)
    )
    snapshot = wait_for_task_status(runtime, task.id, TaskStatus.FAILED)

    assert snapshot.task.summary is not None
    assert "Response-mode tasks must not modify files" in snapshot.task.summary
    assert not (project_root / "README.md").exists()


def test_task_runtime_awaits_approval_and_applies_changes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_git_repo(project_root)

    target = make_target(project_root, approval_required=True)
    runtime = TaskRuntime(
        store=InMemoryStore(),
        target_resolver=StaticTargetResolver(target),
        workspace_manager=WorkspaceManager(state_root=tmp_path / "state"),
        broker=EventBroker(),
        runner=WorktreeRunner(),
    )

    task = runtime.create_task(TaskSubmission(target_id=target.id, prompt="Create a README"))
    snapshot = wait_for_task_status(runtime, task.id, TaskStatus.AWAITING_APPROVAL)

    assert snapshot.run is not None
    assert snapshot.run.diff_path is not None
    assert not (project_root / "README.md").exists()
    assert task.id in runtime.task_workspaces

    approved = runtime.approve_task(task.id, ApprovalAction.APPROVE)

    assert approved.status is TaskStatus.COMPLETED
    assert (project_root / "README.md").exists()
    assert task.id not in runtime.task_workspaces


def test_task_runtime_reject_discards_changes_and_cleans_workspace(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_git_repo(project_root)

    target = make_target(project_root, approval_required=True, auto_create_branch=True)
    runtime = TaskRuntime(
        store=InMemoryStore(),
        target_resolver=StaticTargetResolver(target),
        workspace_manager=WorkspaceManager(state_root=tmp_path / "state"),
        broker=EventBroker(),
        runner=WorktreeRunner(),
    )

    task = runtime.create_task(TaskSubmission(target_id=target.id, prompt="Create a README"))
    wait_for_task_status(runtime, task.id, TaskStatus.AWAITING_APPROVAL)
    workspace = runtime.task_workspaces[task.id]
    assert workspace.worktree_root.exists()

    rejected = runtime.approve_task(task.id, ApprovalAction.REJECT)

    assert rejected.status is TaskStatus.REJECTED
    assert not (project_root / "README.md").exists()
    assert task.id not in runtime.task_workspaces
    assert not workspace.worktree_root.exists()


def test_task_runtime_in_place_runner_can_auto_complete_without_review(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_git_repo(project_root)

    target = make_target(project_root, approval_required=False)
    runtime = TaskRuntime(
        store=InMemoryStore(),
        target_resolver=StaticTargetResolver(target),
        workspace_manager=InPlaceWorkspaceManager(),
        artifact_manager=ArtifactManager(tmp_path / "state"),
        broker=EventBroker(),
        runner=WorktreeRunner(),
    )

    task = runtime.create_task(TaskSubmission(target_id=target.id, prompt="Create a README"))
    snapshot = wait_for_task_status(runtime, task.id, TaskStatus.COMPLETED)

    assert snapshot.task.summary == "Worktree runner completed"
    assert snapshot.run is not None
    assert snapshot.run.exit_code == 0
    assert (project_root / "README.md").exists()
    assert task.id not in runtime.task_workspaces
