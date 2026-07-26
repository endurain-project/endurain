"""Tests for core.timezone module."""

from datetime import UTC, datetime, timedelta, timezone

import core.timezone as core_timezone


class TestToUtcAware:
    """Tests for to_utc_aware function."""

    def test_none_returns_none(self):
        assert core_timezone.to_utc_aware(None) is None

    def test_naive_assumes_utc(self):
        dt = datetime(2025, 1, 15, 10, 30, 0)
        result = core_timezone.to_utc_aware(dt)
        assert result == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_offset_converted_to_utc(self):
        dt = datetime(2026, 3, 28, 8, 19, 19, tzinfo=timezone(timedelta(hours=-7)))
        result = core_timezone.to_utc_aware(dt)
        assert result == datetime(2026, 3, 28, 15, 19, 19, tzinfo=UTC)

    def test_iso_string_parsed(self):
        result = core_timezone.to_utc_aware("2026-03-28T08:19:19-07:00")
        assert result == datetime(2026, 3, 28, 15, 19, 19, tzinfo=UTC)


class TestFormatUtc:
    """Tests for format_utc function."""

    def test_none_returns_empty_string(self):
        assert core_timezone.format_utc(None) == ""

    def test_naive_assumes_utc(self):
        dt = datetime(2025, 1, 15, 10, 30, 0)
        assert core_timezone.format_utc(dt) == "2025-01-15T10:30:00"

    def test_offset_converted_to_utc(self):
        dt = datetime(2026, 3, 28, 8, 19, 19, tzinfo=timezone(timedelta(hours=-7)))
        assert core_timezone.format_utc(dt) == "2026-03-28T15:19:19"

    def test_iso_string_with_offset(self):
        assert core_timezone.format_utc("2026-03-28T08:19:19-07:00") == "2026-03-28T15:19:19"
