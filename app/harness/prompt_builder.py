"""Prompt construction for harness task runs."""

from __future__ import annotations

from app.harness.models import ExecutionTarget
from app.models import Task, TaskMode


class PromptBuilder:
    """Build the structured prompt sent to the configured runner.

    Consumers can replace this with a runner-specific or domain-specific prompt
    builder by implementing `PromptBuilderProtocol`.
    """

    @staticmethod
    def build(task: Task, target: ExecutionTarget) -> str:
        """Build the structured prompt for a single task run.

        The default format is intentionally plain text so it works across
        runner implementations, not only Codex.
        """
        sections = [
            "OBJECTIVE:",
            task.prompt,
            "",
            "TASK MODE:",
            "Response only. Do not modify files in the workspace."
            if task.mode is TaskMode.RESPONSE
            else "Change task. Make the requested workspace updates if needed.",
            "",
            "PROJECT:",
            f"- Name: {target.name or target.id}",
        ]
        if target.path:
            sections.append(f"- Path: {target.path}")
        else:
            sections.append("- Workspace: none")
        if target.context.summary:
            sections.extend(["", "PROJECT CONTEXT:", target.context.summary])
        if task.constraints:
            sections.extend(["", "CONSTRAINTS:"])
            sections.extend(f"- {item}" for item in task.constraints)
        if target.context.extra_constraints:
            if "CONSTRAINTS:" not in sections:
                sections.extend(["", "CONSTRAINTS:"])
            sections.extend(f"- {item}" for item in target.context.extra_constraints)
        if task.acceptance_criteria:
            sections.extend(["", "ACCEPTANCE CRITERIA:"])
            sections.extend(f"- {item}" for item in task.acceptance_criteria)
        if target.context.instructions:
            sections.extend(["", "ADDITIONAL INSTRUCTIONS:", target.context.instructions])
        sections.extend(["", "OUTPUT:", "- Summary"])
        if task.mode is TaskMode.CHANGE:
            sections.append("- List of files changed")
        sections.append("- Execution log")
        return "\n".join(sections)
