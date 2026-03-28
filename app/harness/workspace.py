"""Workspace strategies used by the harness runtime."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, status

from app.harness.models import ExecutionTarget


@dataclass
class TaskWorkspace:
    """Resolved workspace information for one task execution."""

    base_root: Path
    worktree_root: Path
    ref: str
    branch_name: str | None = None


class WorkspaceManager:
    """Prepare isolated git worktrees and apply approved task diffs safely.

    This is the default workspace strategy for CodeClaw-style review flows.
    """

    def __init__(self, state_root: Path | None = None) -> None:
        self.state_root = state_root or Path.home() / ".codeclaw" / "state"

    def prepare(self, target: ExecutionTarget) -> Path:
        """Validate that the configured target path exists and is a git repo."""
        root = Path(target.path).expanduser().resolve()
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

    def prepare_task_workspace(self, target: ExecutionTarget, task_id: str) -> TaskWorkspace:
        """Create a per-task git worktree so execution never touches the base checkout."""
        root = self.prepare(target)
        ref = self._resolve_base_ref(target, root)
        worktree_root = self.state_root / "worktrees" / target.id / task_id
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
        if target.execution.auto_create_branch:
            branch_name = self._branch_name(target, task_id)
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

    def apply_task_changes(self, workspace: TaskWorkspace) -> None:
        """Apply the approved worktree diff back onto the base checkout."""
        if self._has_changes(workspace.base_root):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Base project has uncommitted changes; cannot apply task diff safely",
            )

        patch = self.build_task_patch(workspace)
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

    def cleanup_task_workspace(self, workspace: TaskWorkspace) -> None:
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
    def _resolve_base_ref(target: ExecutionTarget, root: Path) -> str:
        if target.default_branch:
            return target.default_branch

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
    def _branch_name(target: ExecutionTarget, task_id: str) -> str:
        prefix = target.execution.branch_prefix or f"codeclaw/{target.id}"
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
    def build_task_patch(workspace: TaskWorkspace) -> bytes:
        """Stage current workspace changes and return a binary-safe git patch."""
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


class InPlaceWorkspaceManager:
    """Execute tasks directly in the configured workspace without creating a worktree.

    This strategy is useful for consumers that want a simpler harness embedding
    and are comfortable mutating the target path in place.
    """

    def prepare(self, target: ExecutionTarget) -> Path:
        """Validate that the configured target path exists."""
        root = Path(target.path).expanduser().resolve()
        if not root.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workspace path does not exist: {root}",
            )
        return root

    def prepare_task_workspace(self, target: ExecutionTarget, task_id: str) -> TaskWorkspace:
        """Return the target path itself as both base and worktree roots."""
        del task_id
        root = self.prepare(target)
        return TaskWorkspace(
            base_root=root,
            worktree_root=root,
            ref="IN_PLACE",
            branch_name=None,
        )

    def apply_task_changes(self, workspace: TaskWorkspace) -> None:
        """No-op for in-place execution because changes are already applied."""
        del workspace
        return None

    def cleanup_task_workspace(self, workspace: TaskWorkspace) -> None:
        """No-op for in-place execution because no temporary workspace exists."""
        del workspace
        return None
