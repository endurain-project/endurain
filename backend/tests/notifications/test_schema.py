"""Tests for notification Pydantic schemas."""

from datetime import UTC, datetime, timedelta, timezone

import notifications.schema as notifications_schema


class TestNotificationReadCreatedAtSerialization:
    """created_at must serialize as a full UTC ISO 8601 timestamp (issue #775).

    A date-only string is parsed by JavaScript's ``new Date()`` as midnight
    UTC, so the frontend showed notifications as hours old.
    """

    def _notification(self, created_at):
        return notifications_schema.NotificationRead(
            id=1,
            user_id=1,
            type=1,
            options=None,
            read=False,
            created_at=created_at,
        )

    def test_created_at_serializes_full_iso_with_utc_offset(self):
        value = datetime(2026, 7, 16, 10, 30, 0, tzinfo=UTC)

        dumped = self._notification(value).model_dump()

        assert dumped["created_at"] == "2026-07-16T10:30:00+00:00"

    def test_created_at_naive_datetime_assumed_utc(self):
        value = datetime(2026, 7, 16, 10, 30, 0)

        dumped = self._notification(value).model_dump()

        assert dumped["created_at"] == "2026-07-16T10:30:00+00:00"

    def test_created_at_non_utc_offset_normalized_to_utc(self):
        value = datetime(2026, 7, 16, 8, 19, 0, tzinfo=timezone(timedelta(hours=-7)))

        dumped = self._notification(value).model_dump()

        assert dumped["created_at"] == "2026-07-16T15:19:00+00:00"

    def test_created_at_none_serializes_none(self):
        dumped = self._notification(None).model_dump()

        assert dumped["created_at"] is None
