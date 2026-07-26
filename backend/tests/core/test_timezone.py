"""Tests for core.timezone module."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

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


class TestTodayIn:
    """ "Which day is it?" must be answered in an explicit zone, never the server's."""

    def test_returns_a_date(self):
        from datetime import date

        assert isinstance(core_timezone.today_in("UTC"), date)

    def test_zones_either_side_of_the_dateline_can_disagree(self):
        """The whole point: two athletes can be on different calendar days."""
        east = core_timezone.today_in("Pacific/Kiritimati")  # UTC+14
        west = core_timezone.today_in("Pacific/Niue")  # UTC-11
        assert (east - west).days in (0, 1)

    def test_matches_an_explicit_conversion(self):
        from datetime import UTC, datetime
        from zoneinfo import ZoneInfo

        expected = datetime.now(UTC).astimezone(ZoneInfo("Asia/Tokyo")).date()
        assert core_timezone.today_in("Asia/Tokyo") == expected

    def test_rejects_an_unknown_zone(self):
        from zoneinfo import ZoneInfoNotFoundError

        with pytest.raises(ZoneInfoNotFoundError):
            core_timezone.today_in("Not/AZone")
