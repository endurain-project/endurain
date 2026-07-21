"""Tests for activity ingestion-contract schemas (ParsedActivity)."""

from datetime import datetime, timedelta, timezone

from modules.activities.activity.schema import Activity, ParsedActivity


def _activity(start, end):
    return Activity(distance=1000, name="Test", activity_type=1, start_time=start, end_time=end)


class TestParsedActivityDatetimeNormalization:
    """__post_init__ guarantees timezone-aware UTC datetimes for every source."""

    def test_naive_datetimes_become_utc_aware(self):
        parsed = ParsedActivity(
            activity=_activity(datetime(2026, 6, 20, 8, 0, 0), datetime(2026, 6, 20, 9, 0, 0)),
        )

        assert parsed.activity.start_time.tzinfo is not None
        assert parsed.activity.start_time.utcoffset() == timedelta(0)
        assert parsed.activity.end_time.utcoffset() == timedelta(0)
        # Naive wall-clock is interpreted as UTC (no shift).
        assert parsed.activity.start_time.hour == 8

    def test_offset_aware_datetimes_converted_to_utc(self):
        # 08:00 at +02:00 == 06:00 UTC.
        tz_plus_two = timezone(timedelta(hours=2))
        parsed = ParsedActivity(
            activity=_activity(
                datetime(2026, 6, 20, 8, 0, 0, tzinfo=tz_plus_two),
                datetime(2026, 6, 20, 9, 0, 0, tzinfo=tz_plus_two),
            ),
        )

        assert parsed.activity.start_time.utcoffset() == timedelta(0)
        assert parsed.activity.start_time.hour == 6
        assert parsed.activity.end_time.hour == 7

    def test_iso_string_datetimes_normalized(self):
        parsed = ParsedActivity(activity=_activity("2026-06-20T08:00:00", "2026-06-20T09:00:00"))

        assert isinstance(parsed.activity.start_time, datetime)
        assert parsed.activity.start_time.tzinfo is not None
        assert parsed.activity.start_time.utcoffset() == timedelta(0)

    def test_none_datetimes_stay_none(self):
        parsed = ParsedActivity(activity=_activity(None, None))

        assert parsed.activity.start_time is None
        assert parsed.activity.end_time is None
