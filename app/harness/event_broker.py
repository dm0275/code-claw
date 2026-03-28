from __future__ import annotations

from queue import Empty, Queue
from typing import Iterator

from app.models import TaskEvent


class EventBroker:
    """Fan out task events to any active SSE subscribers."""

    def __init__(self) -> None:
        self._streams: dict[str, list[Queue[TaskEvent]]] = {}

    def publish(self, event: TaskEvent) -> None:
        for queue in self._streams.get(event.task_id, []):
            queue.put(event)

    def subscribe(self, task_id: str) -> Iterator[TaskEvent]:
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
