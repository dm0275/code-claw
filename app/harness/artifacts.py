"""Artifact persistence helpers for harness task runs.

This module keeps diff and log persistence separate from workspace setup so a
consumer can replace storage behavior without replacing the workspace strategy.
"""

from __future__ import annotations

from pathlib import Path

from app.harness.state import Run
from app.harness.workspace import TaskWorkspace, WorkspaceManager


class ArtifactManager:
    """Persist durable review artifacts independently from git workspace operations.

    The default implementation writes:
    - `stdout.jsonl`
    - `stderr.jsonl`
    - `diff.patch`

    under a per-task artifact directory beneath `state_root`.
    """

    def __init__(self, state_root: Path | None = None) -> None:
        self.state_root = state_root or Path.home() / ".harness" / "state"

    def persist_task_artifacts(self, task_id: str, workspace: TaskWorkspace, run: Run) -> Run:
        """Write task logs and the staged patch to durable artifact files.

        The returned `Run` is the same instance with the artifact paths populated.
        """
        artifact_dir = self.state_root / "artifacts" / task_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        stdout_path = artifact_dir / "stdout.jsonl"
        stderr_path = artifact_dir / "stderr.jsonl"
        diff_path = artifact_dir / "diff.patch"

        stdout_contents = "\n".join(run.stdout) + ("\n" if run.stdout else "")
        stderr_contents = "\n".join(run.stderr) + ("\n" if run.stderr else "")
        stdout_path.write_text(stdout_contents, encoding="utf-8")
        stderr_path.write_text(stderr_contents, encoding="utf-8")
        diff_path.write_bytes(WorkspaceManager.build_task_patch(workspace))

        run.stdout_path = str(stdout_path)
        run.stderr_path = str(stderr_path)
        run.diff_path = str(diff_path)
        return run
