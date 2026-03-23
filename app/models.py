from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class ApprovalAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=1024)
    branch: Optional[str] = Field(default=None, max_length=255)


class Workspace(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    path: str
    branch: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def root(self) -> Path:
        return Path(self.path).expanduser().resolve()


class TaskCreate(BaseModel):
    workspace_id: str
    prompt: str = Field(min_length=1)
    constraints: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)


class Task(BaseModel):
    id: str = Field(default_factory=new_id)
    workspace_id: str
    prompt: str
    constraints: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    summary: Optional[str] = None
    files_modified: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None


class Run(BaseModel):
    id: str = Field(default_factory=new_id)
    task_id: str
    cwd: str
    structured_prompt: str
    status: TaskStatus = TaskStatus.PENDING
    exit_code: Optional[int] = None
    stdout: List[str] = Field(default_factory=list)
    stderr: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None


class TaskEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    task_id: str
    type: str
    message: str
    timestamp: datetime = Field(default_factory=utc_now)


class ApprovalRequest(BaseModel):
    action: ApprovalAction


class TaskDetail(BaseModel):
    task: Task
    run: Optional[Run] = None
    recent_events: List[TaskEvent] = Field(default_factory=list)
