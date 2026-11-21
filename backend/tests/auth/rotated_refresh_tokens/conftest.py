"""Fixtures of this module's tests."""

import jasil.runtime as jasil_runtime
import pytest
from jasil.events import Event


@pytest.fixture
def published():
    """Return a function that records the events of the given types the application publishes from now on."""

    def listen(*event_types: str) -> list[Event]:
        events: list[Event] = []
        bus = jasil_runtime.get_active_platform().events
        for event_type in event_types:
            bus.subscribe(event_type, events.append)
        return events

    return listen
