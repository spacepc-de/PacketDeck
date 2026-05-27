import asyncio
from collections.abc import AsyncIterator
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AppEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "app"
    severity: str = "info"
    id: str = field(default_factory=lambda: str(uuid4()))


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[AppEvent]] = set()
        self._events: deque[AppEvent] = deque(maxlen=5000)

    async def publish(self, event: AppEvent) -> None:
        self._events.append(event)
        stale: list[asyncio.Queue[AppEvent]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self._subscribers.discard(queue)

    async def subscribe(self) -> AsyncIterator[AppEvent]:
        queue: asyncio.Queue[AppEvent] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)

    def list_events(
        self,
        *,
        window_seconds: int = 300,
        limit: int = 200,
        source: str | None = None,
        event_type: str | None = None,
    ) -> list[AppEvent]:
        since = datetime.now(UTC) - timedelta(seconds=window_seconds)
        events = [
            event
            for event in self._events
            if event.created_at >= since
            and (source is None or event.source == source)
            and (event_type is None or event.type == event_type)
        ]
        return events[-limit:]


event_bus = EventBus()
