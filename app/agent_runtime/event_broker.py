"""In-process task event fanout for the agent runtime.

The broker is intentionally simple: publishers send `TaskEvent` objects and
subscribers receive live events plus periodic heartbeat messages while idle.
"""

from __future__ import annotations

from queue import Empty, Queue
from typing import Iterator

from app.agent_runtime.state import TaskEvent


class EventBroker:
    """Fan out task events to any active SSE subscribers."""

    def __init__(self) -> None:
        self._streams: dict[str, list[Queue[TaskEvent]]] = {}

    def publish(self, event: TaskEvent) -> None:
        """Deliver one event to any current subscribers for the same task."""
        for queue in self._streams.get(event.task_id, []):
            queue.put(event)

    def subscribe(self, task_id: str) -> Iterator[TaskEvent]:
        """Yield live events for one task.

        Idle subscribers receive heartbeat events every 15 seconds so callers can
        keep long-lived streams open without inferring liveness from silence.
        """
        queue: Queue[TaskEvent] = Queue()
        self._streams.setdefault(task_id, []).append(queue)
        try:
            while True:
                try:
                    yield queue.get(timeout=15)
                except Empty:
                    yield TaskEvent(task_id=task_id, type="heartbeat", message="waiting")
        finally:
            self._streams[task_id].remove(queue)
            if not self._streams[task_id]:
                self._streams.pop(task_id, None)
