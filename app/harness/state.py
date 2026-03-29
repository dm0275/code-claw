"""Harness-owned lifecycle records and enums.

These models define the runtime state contract used by the reusable harness so
the package does not need to import task/run/event types from a host app.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
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


class Task(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    prompt: str
    mode: TaskMode = TaskMode.CHANGE
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    summary: Optional[str] = None
    files_modified: list[str] = Field(default_factory=list)
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
    stdout: list[str] = Field(default_factory=list)
    stderr: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None


class TaskEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    task_id: str
    type: str
    message: str
    timestamp: datetime = Field(default_factory=utc_now)
