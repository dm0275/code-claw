from __future__ import annotations

from app.harness.models import ExecutionTarget
from app.models import Task


class PromptBuilder:
    @staticmethod
    def build(task: Task, target: ExecutionTarget) -> str:
        """Build the structured prompt sent to Codex for a single task run."""
        sections = [
            "OBJECTIVE:",
            task.prompt,
            "",
            "PROJECT:",
            f"- Name: {target.name or target.id}",
            f"- Path: {target.path}",
        ]
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
        sections.extend(
            [
                "",
                "OUTPUT:",
                "- Summary",
                "- List of files changed",
                "- Execution log",
            ]
        )
        return "\n".join(sections)
