from __future__ import annotations

from typing import List, Optional

from pydantic import AliasChoices, BaseModel, Field

from app.models import (
    ApprovalAction,
    Project,
    ProjectContext,
    ProjectExecution,
    Run,
    Task,
    TaskEvent,
)


class ProjectRegistration(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    default_branch: Optional[str] = None
    execution: ProjectExecution = Field(default_factory=ProjectExecution)
    context: ProjectContext = Field(default_factory=ProjectContext)


class TaskCreate(BaseModel):
    project_id: str = Field(validation_alias=AliasChoices("project_id", "workspace_id"))
    prompt: str = Field(min_length=1)
    constraints: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    action: ApprovalAction


class TaskDetail(BaseModel):
    task: Task
    run: Optional[Run] = None
    recent_events: List[TaskEvent] = Field(default_factory=list)


__all__ = [
    "ApprovalRequest",
    "Project",
    "ProjectRegistration",
    "Task",
    "TaskCreate",
    "TaskDetail",
]
