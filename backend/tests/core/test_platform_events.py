"""Tests for core.platform.events."""

import uuid
from datetime import datetime

import core.platform.events as platform_events


class TestEvent:
    def test_is_frozen(self):
        event = platform_events.new_event("t", {}, source="s")
        assert event.__dataclass_params__.frozen is True

    def test_defaults(self):
        event = platform_events.Event(event_id="id", event_type="t", source="s", timestamp="ts", payload={})
        assert event.metadata == {}
        assert event.retry_count == 0


class TestNewEvent:
    def test_mints_uuid_and_timestamp(self):
        event = platform_events.new_event("activity.created", {"activity_id": 42}, source="api:store_activity")
        assert uuid.UUID(event.event_id)  # parses as a valid UUID
        parsed = datetime.fromisoformat(event.timestamp)
        assert parsed.tzinfo is not None
        assert event.event_type == "activity.created"
        assert event.payload == {"activity_id": 42}
        assert event.source == "api:store_activity"
        assert event.metadata == {}
        assert event.retry_count == 0

    def test_ids_are_unique(self):
        first = platform_events.new_event("t", {}, source="s")
        second = platform_events.new_event("t", {}, source="s")
        assert first.event_id != second.event_id

    def test_explicit_id_metadata_retry(self):
        event = platform_events.new_event(
            "t",
            {"k": 1},
            source="s",
            metadata={"request_id": "r"},
            event_id="fixed",
            retry_count=2,
        )
        assert event.event_id == "fixed"
        assert event.metadata == {"request_id": "r"}
        assert event.retry_count == 2


class TestConstants:
    def test_metadata_key_constants(self):
        assert platform_events.META_REQUEST_ID == "request_id"
        assert platform_events.META_USER_ID == "user_id"
        assert platform_events.META_ACTIVITY_ID == "activity_id"
