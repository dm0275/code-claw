"""Reusable agent runtime package for agent-run execution.

Typical usage for external consumers is:

```python
from app.agent_runtime import (
    CodexRunner,
    EventBroker,
    ExecutionTarget,
    TargetExecutionSettings,
    TaskRuntime,
    TaskSubmission,
    WorkspaceManager,
)
```

The package can be used directly by any host application that wants a reusable
agent-execution workflow around a local workspace.
"""

from app.agent_runtime.artifacts import ArtifactManager
from app.agent_runtime.event_broker import EventBroker
from app.agent_runtime.models import (
    ExecutionTarget,
    RunnerResult,
    TargetContext,
    TargetExecutionSettings,
    TaskSnapshot,
    TaskSubmission,
)
from app.agent_runtime.prompt_builder import PromptBuilder
from app.agent_runtime.protocols import (
    ArtifactManagerProtocol,
    EventBrokerProtocol,
    PromptBuilderProtocol,
    RunnerProtocol,
    TargetResolverProtocol,
    WorkspaceManagerProtocol,
)
from app.agent_runtime.runners import CodexRunner
from app.agent_runtime.state import ApprovalAction, Run, Task, TaskEvent, TaskMode, TaskStatus
from app.agent_runtime.store import RuntimeStoreProtocol
from app.agent_runtime.task_runtime import TaskRuntime
from app.agent_runtime.workspace import (
    InPlaceWorkspaceManager,
    NoWorkspaceManager,
    TaskWorkspace,
    WorkspaceManager,
)

__all__ = [
    "ApprovalAction",
    "ArtifactManager",
    "ArtifactManagerProtocol",
    "CodexRunner",
    "ExecutionTarget",
    "EventBroker",
    "EventBrokerProtocol",
    "InPlaceWorkspaceManager",
    "NoWorkspaceManager",
    "PromptBuilder",
    "PromptBuilderProtocol",
    "Run",
    "RunnerResult",
    "RunnerProtocol",
    "RuntimeStoreProtocol",
    "Task",
    "TaskEvent",
    "TaskMode",
    "TaskStatus",
    "TargetContext",
    "TargetExecutionSettings",
    "TargetResolverProtocol",
    "TaskRuntime",
    "TaskWorkspace",
    "TaskSnapshot",
    "TaskSubmission",
    "WorkspaceManager",
    "WorkspaceManagerProtocol",
]
