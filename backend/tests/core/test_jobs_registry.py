"""Tests for the durable-job handler registry."""

import core.platform.events as platform_events
from core.jobs.registry import JobHandlerRegistry


def _handler(event: platform_events.Event) -> None:  # pragma: no cover - never invoked
    return None


class TestJobHandlerRegistry:
    def test_register_and_get(self):
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", _handler)
        assert reg.get("sub.a") is _handler

    def test_get_unknown_returns_none(self):
        assert JobHandlerRegistry().get("nope") is None

    def test_register_replaces_existing(self):
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", _handler)
        other = lambda event: None  # noqa: E731 - test double
        reg.register("activity.created", "sub.a", other)
        assert reg.get("sub.a") is other

    def test_subscribers_for_lists_ids_in_order(self):
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", _handler)
        reg.register("activity.created", "sub.b", _handler)
        reg.register("activity.deleted", "sub.c", _handler)
        assert reg.subscribers_for("activity.created") == ("sub.a", "sub.b")
        assert reg.subscribers_for("activity.deleted") == ("sub.c",)
        assert reg.subscribers_for("unknown") == ()

    def test_register_is_idempotent_per_event_type(self):
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", _handler)
        reg.register("activity.created", "sub.a", _handler)
        assert reg.subscribers_for("activity.created") == ("sub.a",)

    def test_clear(self):
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", _handler)
        reg.clear()
        assert reg.get("sub.a") is None
        assert reg.subscribers_for("activity.created") == ()
