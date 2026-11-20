"""In-memory SSE subscriber registry and wire formatting for generation events.

The jobs manager publishes one event per generation; the API layer turns those
events into the ``text/event-stream`` body described in ARCHITECTURE.md §9.2.
The registry lives in the process, so a reconnecting client is served the
current state again instead of a gap in the history (§7.8).
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

RETRY_LINE = "retry: 3000\n\n"
"""Reconnect hint sent once when an event stream opens (§9.2)."""


@dataclass(frozen=True)
class SseEvent:
    """One named SSE event with its JSON payload."""

    name: str
    data: dict[str, Any]
    terminal: bool = False

    def to_wire(self) -> str:
        """Serialize the event as an SSE frame (§9.2)."""
        payload = json.dumps(self.data, separators=(",", ":"))
        return f"event: {self.name}\ndata: {payload}\n\n"


class Subscriber:
    """A queue of events for one generation id."""

    def __init__(self, generation_id: str) -> None:
        self.generation_id = generation_id
        self._queue: queue.Queue[SseEvent | None] = queue.Queue()

    def put(self, event: SseEvent) -> None:
        """Queue an event for the subscriber."""
        self._queue.put(event)

    def close(self) -> None:
        """Signal the end of the stream."""
        self._queue.put(None)

    def events(self) -> Iterator[SseEvent | None]:
        """Yield queued events until the stream is closed."""
        while True:
            event = self._queue.get()
            yield event
            if event is None:
                return

    def get(self, timeout: float | None = None) -> SseEvent | None:
        """Pop the next event, waiting at most ``timeout`` seconds.

        Raises :class:`queue.Empty` when no event arrives in time; ``None``
        marks the end of the stream.
        """
        return self._queue.get(timeout=timeout)


class EventBus:
    """Registry of SSE subscribers, keyed by generation id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[Subscriber]] = {}

    def subscribe(self, generation_id: str) -> Subscriber:
        """Register a new subscriber for a generation."""
        with self._lock:
            subscriber = Subscriber(generation_id)
            self._subscribers.setdefault(generation_id, []).append(subscriber)
            return subscriber

    def unsubscribe(self, generation_id: str, subscriber: Subscriber) -> None:
        """Forget a subscriber without ending any other stream."""
        with self._lock:
            subscribers = self._subscribers.get(generation_id)
            if not subscribers:
                return
            if subscriber in subscribers:
                subscribers.remove(subscriber)
            if not subscribers:
                del self._subscribers[generation_id]

    def publish(self, generation_id: str, event: SseEvent) -> None:
        """Deliver an event to every subscriber of a generation."""
        with self._lock:
            for subscriber in list(self._subscribers.get(generation_id, ())):
                subscriber.put(event)

    def close(self, generation_id: str) -> None:
        """End every stream of a generation after its terminal event."""
        with self._lock:
            subscribers = self._subscribers.pop(generation_id, [])
        for subscriber in subscribers:
            subscriber.close()

    def close_all(self) -> None:
        """End every open stream, for example when the process shuts down."""
        with self._lock:
            generation_ids = list(self._subscribers)
        for generation_id in generation_ids:
            self.close(generation_id)
