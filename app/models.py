from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from app.agent_runtime.state import (
    ApprovalAction as HarnessApprovalAction,
)
from app.agent_runtime.state import (
    Run as HarnessRun,
)
from app.agent_runtime.state import (
    Task as HarnessTask,
)
from app.agent_runtime.state import (
    TaskEvent as HarnessTaskEvent,
)
from app.agent_runtime.state import (
    TaskMode as HarnessTaskMode,
)
from app.agent_runtime.state import (
    TaskStatus as HarnessTaskStatus,
)
from app.agent_runtime.state import (
    new_id as harness_new_id,
)
from app.agent_runtime.state import (
    utc_now,
)

ApprovalAction = HarnessApprovalAction
new_id = harness_new_id
Run = HarnessRun
Task = HarnessTask
TaskEvent = HarnessTaskEvent
TaskMode = HarnessTaskMode
TaskStatus = HarnessTaskStatus


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
