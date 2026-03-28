from __future__ import annotations

from app.models import Project, Task


class PromptBuilder:
    @staticmethod
    def build(task: Task, project: Project) -> str:
        """Build the structured prompt sent to Codex for a single task run."""
        sections = [
            "OBJECTIVE:",
            task.prompt,
            "",
            "PROJECT:",
            f"- Name: {project.name}",
            f"- Path: {project.path}",
        ]
        if project.context.summary:
            sections.extend(["", "PROJECT CONTEXT:", project.context.summary])
        if task.constraints:
            sections.extend(["", "CONSTRAINTS:"])
            sections.extend(f"- {item}" for item in task.constraints)
        if project.context.extra_constraints:
            if "CONSTRAINTS:" not in sections:
                sections.extend(["", "CONSTRAINTS:"])
            sections.extend(f"- {item}" for item in project.context.extra_constraints)
        if task.acceptance_criteria:
            sections.extend(["", "ACCEPTANCE CRITERIA:"])
            sections.extend(f"- {item}" for item in task.acceptance_criteria)
        if project.context.instructions:
            sections.extend(["", "ADDITIONAL INSTRUCTIONS:", project.context.instructions])
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
