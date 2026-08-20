"""Tests for the activity ingestion contract (ActivityCore, ParsedActivity)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from modules.activities.activity.contracts import ActivityCore, ParsedActivity


def _core(start, end, **overrides):
    data = {
        "user_id": 1,
        "distance": 1000,
        "name": "Test",
        "activity_type": 1,
        "start_time": start,
        "end_time": end,
    }
    data.update(overrides)
    return ActivityCore(**data)


class TestActivityCoreDatetimeNormalization:
    """The ActivityCore validator coerces start/end to timezone-aware UTC.

    Normalization that used to run in ``ParsedActivity.__post_init__`` now happens
    at ActivityCore construction (the ingestion boundary), so persistence and
    serialization never see a naive datetime regardless of the source.
    """

    def test_naive_datetimes_become_utc_aware(self):
        core = _core(datetime(2026, 6, 20, 8, 0, 0), datetime(2026, 6, 20, 9, 0, 0))

        assert core.start_time.tzinfo is not None
        assert core.start_time.utcoffset() == timedelta(0)
        assert core.end_time.utcoffset() == timedelta(0)
        # Naive wall-clock is interpreted as UTC (no shift).
        assert core.start_time.hour == 8

    def test_offset_aware_datetimes_converted_to_utc(self):
        # 08:00 at +02:00 == 06:00 UTC.
        tz_plus_two = timezone(timedelta(hours=2))
        core = _core(
            datetime(2026, 6, 20, 8, 0, 0, tzinfo=tz_plus_two),
            datetime(2026, 6, 20, 9, 0, 0, tzinfo=tz_plus_two),
        )

        assert core.start_time.utcoffset() == timedelta(0)
        assert core.start_time.hour == 6
        assert core.end_time.hour == 7

    def test_iso_string_datetimes_normalized(self):
        core = _core("2026-06-20T08:00:00", "2026-06-20T09:00:00")

        assert isinstance(core.start_time, datetime)
        assert core.start_time.tzinfo is not None
        assert core.start_time.utcoffset() == timedelta(0)


class TestActivityCoreStrictRequired:
    """ActivityCore rejects a missing owner or null/absent start/end at the boundary."""

    def test_none_start_time_rejected(self):
        with pytest.raises(ValidationError):
            _core(None, datetime(2026, 6, 20, 9, 0, 0, tzinfo=UTC))

    def test_none_end_time_rejected(self):
        with pytest.raises(ValidationError):
            _core(datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC), None)

    def test_missing_start_time_rejected(self):
        with pytest.raises(ValidationError):
            ActivityCore(user_id=1, distance=1000, name="Test", activity_type=1, end_time="2026-06-20T09:00:00")

    def test_missing_end_time_rejected(self):
        with pytest.raises(ValidationError):
            ActivityCore(user_id=1, distance=1000, name="Test", activity_type=1, start_time="2026-06-20T08:00:00")

    def test_missing_user_id_rejected(self):
        with pytest.raises(ValidationError):
            ActivityCore(
                distance=1000,
                name="Test",
                activity_type=1,
                start_time="2026-06-20T08:00:00",
                end_time="2026-06-20T09:00:00",
            )


class TestServerOwnedFieldsAreNotIngestionInputs:
    """``ActivityCore`` extends the shared base, not the read model.

    While it inherited from the read ``Activity``, every field added for the API
    silently became an accepted ingestion input — including the ones only the
    server may set. Extending ``ActivityBase`` instead is what keeps that from
    happening again as the read model grows.
    """

    def test_read_model_exposes_the_server_owned_fields(self):
        from modules.activities.activity.schema import Activity

        assert "id" in Activity.model_fields
        assert "map_thumbnail_path" in Activity.model_fields

    def test_ingestion_contract_does_not(self):
        assert "id" not in ActivityCore.model_fields
        assert "map_thumbnail_path" not in ActivityCore.model_fields

    def test_a_producer_cannot_set_them(self):
        core = _core("2026-06-20T08:00:00", "2026-06-20T09:00:00")
        # Re-built with the server-owned fields supplied: they are dropped, not
        # honoured, so no producer can claim an id or a thumbnail key.
        smuggled = ActivityCore(
            **core.model_dump(),
            id=999,
            map_thumbnail_path="thumbnails/999.png",
        )

        assert not hasattr(smuggled, "id")
        assert not hasattr(smuggled, "map_thumbnail_path")


class TestParsedActivity:
    """ParsedActivity carries the strict ActivityCore as its activity."""

    def test_holds_activity_core(self):
        core = _core("2026-06-20T08:00:00", "2026-06-20T09:00:00")
        parsed = ParsedActivity(activity=core)

        assert parsed.activity is core
        assert parsed.components == {}
