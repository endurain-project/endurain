"""Tests for notification Pydantic schemas."""

from datetime import UTC, datetime, timedelta, timezone

import modules.notifications.schema as notifications_schema


class TestNotificationReadCreatedAt:
    """created_at is normalized to UTC and serializes as a full ISO 8601 timestamp."""

    def _notification(self, created_at):
        return notifications_schema.NotificationRead(
            id=1,
            user_id=1,
            type=1,
            options=None,
            read=False,
            created_at=created_at,
        )

    def test_json_dump_is_full_iso_with_utc_offset(self):
        value = datetime(2026, 7, 16, 10, 30, 0, tzinfo=UTC)

        dumped = self._notification(value).model_dump(mode="json")

        assert dumped["created_at"] == "2026-07-16T10:30:00Z"

    def test_python_dump_keeps_datetime(self):
        value = datetime(2026, 7, 16, 10, 30, 0, tzinfo=UTC)

        dumped = self._notification(value).model_dump()

        assert dumped["created_at"] == value
        assert isinstance(dumped["created_at"], datetime)

    def test_naive_datetime_assumed_utc(self):
        value = datetime(2026, 7, 16, 10, 30, 0)

        notification = self._notification(value)

        assert notification.created_at == datetime(2026, 7, 16, 10, 30, 0, tzinfo=UTC)

    def test_non_utc_offset_normalized_to_utc(self):
        value = datetime(2026, 7, 16, 8, 19, 0, tzinfo=timezone(timedelta(hours=-7)))

        dumped = self._notification(value).model_dump(mode="json")

        assert dumped["created_at"] == "2026-07-16T15:19:00Z"

    def test_none_stays_none(self):
        dumped = self._notification(None).model_dump(mode="json")

        assert dumped["created_at"] is None
