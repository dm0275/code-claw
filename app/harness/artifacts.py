from __future__ import annotations

from pathlib import Path

from app.harness.workspace import TaskWorkspace, WorkspaceManager
from app.models import Run


class ArtifactManager:
    """Persist durable review artifacts independently from git workspace operations."""

    def __init__(self, state_root: Path | None = None) -> None:
        self.state_root = state_root or Path.home() / ".codeclaw" / "state"

    def persist_task_artifacts(self, task_id: str, workspace: TaskWorkspace, run: Run) -> Run:
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
        diff_path.write_bytes(WorkspaceManager.build_task_patch(workspace))

        run.stdout_path = str(stdout_path)
        run.stderr_path = str(stderr_path)
        run.diff_path = str(diff_path)
        return run
