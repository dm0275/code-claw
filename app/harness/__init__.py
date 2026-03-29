"""Reusable harness package for agent-run execution against a local workspace.

Typical usage for external consumers is:

```python
from app.harness import (
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

from app.harness.artifacts import ArtifactManager
from app.harness.event_broker import EventBroker
from app.harness.models import (
    ExecutionTarget,
    RunnerResult,
    TargetContext,
    TargetExecutionSettings,
    TaskSnapshot,
    TaskSubmission,
)
from app.harness.prompt_builder import PromptBuilder
from app.harness.protocols import (
    ArtifactManagerProtocol,
    EventBrokerProtocol,
    PromptBuilderProtocol,
    RunnerProtocol,
    TargetResolverProtocol,
    WorkspaceManagerProtocol,
)
from app.harness.runners import CodexRunner
from app.harness.task_runtime import TaskRuntime
from app.harness.workspace import (
    InPlaceWorkspaceManager,
    NoWorkspaceManager,
    TaskWorkspace,
    WorkspaceManager,
)

__all__ = [
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
    "RunnerResult",
    "RunnerProtocol",
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
