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


class TaskMode(str, Enum):
    CHANGE = "change"
    RESPONSE = "response"


class ProjectExecution(BaseModel):
    sandbox: str = "workspace-write"
    approval_required: bool = True
    auto_create_branch: bool = False
    branch_prefix: Optional[str] = None
    extra_writable_dirs: List[str] = Field(default_factory=list)


class ProjectContext(BaseModel):
    summary: Optional[str] = None
    extra_constraints: List[str] = Field(default_factory=list)
    instructions: Optional[str] = None


class Project(BaseModel):
    id: str
    name: str
    path: str
    enabled: bool = True
    default_branch: Optional[str] = None
    project_dir: Optional[str] = None
    execution: ProjectExecution = Field(default_factory=ProjectExecution)
    context: ProjectContext = Field(default_factory=ProjectContext)
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def root(self) -> Path:
        return Path(self.path).expanduser().resolve()


class Task(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    prompt: str
    mode: TaskMode = TaskMode.CHANGE
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
    base_cwd: Optional[str] = None
    target_branch: Optional[str] = None
    diff_path: Optional[str] = None
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
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
