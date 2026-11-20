"""Unit tests for the SSE subscriber registry and wire format."""

from __future__ import annotations

import json
import queue

import pytest

from tts.jobs.sse import RETRY_LINE, EventBus, SseEvent, Subscriber


def test_event_serializes_to_an_sse_frame() -> None:
    event = SseEvent(name="progress", data={"generationId": "abc", "status": "running"})

    wire = event.to_wire()

    assert wire.startswith("event: progress\n")
    assert wire.endswith("\n\n")
    payload_line = next(line for line in wire.splitlines() if line.startswith("data: "))
    assert json.loads(payload_line.removeprefix("data: ")) == {
        "generationId": "abc",
        "status": "running",
    }


def test_retry_line_is_a_single_reconnect_hint() -> None:
    assert RETRY_LINE == "retry: 3000\n\n"


def test_subscriber_yields_events_until_the_stream_closes() -> None:
    subscriber = Subscriber("generation-1")
    first = SseEvent(name="progress", data={"generationId": "generation-1"})
    second = SseEvent(name="succeeded", data={"generationId": "generation-1"}, terminal=True)

    subscriber.put(first)
    subscriber.put(second)
    subscriber.close()

    assert list(subscriber.events()) == [first, second, None]


def test_bus_delivers_to_every_subscriber_of_a_generation() -> None:
    bus = EventBus()
    first = bus.subscribe("generation-1")
    second = bus.subscribe("generation-1")
    other = bus.subscribe("generation-2")

    bus.publish("generation-1", SseEvent(name="progress", data={"generationId": "generation-1"}))

    assert first.get(timeout=1) is not None
    assert second.get(timeout=1) is not None
    with pytest.raises(queue.Empty):
        other.get(timeout=0.05)


def test_bus_close_ends_every_stream_of_a_generation() -> None:
    bus = EventBus()
    subscriber = bus.subscribe("generation-1")

    bus.publish("generation-1", SseEvent(name="succeeded", data={}, terminal=True))
    bus.close("generation-1")

    events = list(subscriber.events())
    assert events[-1] is None
    assert events[0].name == "succeeded"


def test_bus_unsubscribe_forgets_only_that_subscriber() -> None:
    bus = EventBus()
    first = bus.subscribe("generation-1")
    second = bus.subscribe("generation-1")

    bus.unsubscribe("generation-1", first)
    bus.publish("generation-1", SseEvent(name="progress", data={}))

    assert second.get(timeout=1) is not None
    with pytest.raises(queue.Empty):
        first.get(timeout=0.05)


def test_bus_close_all_ends_every_open_stream() -> None:
    bus = EventBus()
    subscriber = bus.subscribe("generation-1")

    bus.close_all()

    assert list(subscriber.events()) == [None]
