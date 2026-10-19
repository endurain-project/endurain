"""Tests for ``activities.activity.serializers`` (ORM→schema + visibility masking)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _activity_orm_stub():
    """An ORM-shaped object carrying only the attributes the serializer reads.

    A ``SimpleNamespace`` rather than a ``MagicMock`` so ``model_validate`` sees
    real values (a MagicMock hands back child mocks for every optional field and
    fails validation), and rather than a real ORM row so the test does not need
    the whole mapper registry configured.
    """
    return SimpleNamespace(
        id=1,
        user_id=1,
        distance=1000,
        name="Ride",
        activity_type=5,
        timezone="Asia/Tokyo",
        map_thumbnail_path=None,
        start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
        created_at=datetime(2024, 1, 15, 7, 0, 0, tzinfo=UTC),
    )


class TestSerializeActivity:
    @patch("modules.activities.activity.serializers.activity_schema.ActivityRead")
    def test_serialize_basic(self, mock_schema_cls):
        from modules.activities.activity.serializers import to_read_schema

        mock_schema = MagicMock()
        mock_schema_cls.model_validate.return_value = mock_schema

        activity = MagicMock()
        activity.timezone = "Europe/Lisbon"
        activity.map_thumbnail_path = "1.webp"

        result = to_read_schema(activity)

        # The key stays a key: turning it into a URL is the service's job.
        assert result is mock_schema
        mock_schema_cls.model_validate.assert_called_once_with(activity)

    def test_datetimes_are_aware_utc_instants(self):
        """The API emits real instants; localizing for display is the client's job."""
        from modules.activities.activity.serializers import to_read_schema

        activity = _activity_orm_stub()

        result = to_read_schema(activity)

        assert result.start_time == datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)
        assert result.end_time == datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
        assert result.created_at == datetime(2024, 1, 15, 7, 0, 0, tzinfo=UTC)
        # The zone travels alongside, so a client can render the athlete's local
        # wall clock without the server pre-formatting anything.
        assert result.timezone == "Asia/Tokyo"


class TestApplyVisibilityMask:
    def test_owner_no_mask(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "secret"
        schema.hide_start_time = True
        schema.hide_location = True
        schema.hide_gear = True

        result = apply_visibility_mask(schema, is_owner=True)

        assert result.private_notes == "secret"

    def test_non_owner_masks_private_notes(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "secret"

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.private_notes is None

    def test_non_owner_masks_hidden_fields(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.hide_start_time = True
        schema.start_time = "2024-01-15T08:00:00"
        schema.end_time = "2024-01-15T09:00:00"
        schema.hide_location = True
        schema.city = "City"
        schema.town = "Town"
        schema.country = "Country"
        schema.hide_gear = True
        schema.gear_id = 1
        schema.strava_gear_id = "g1"
        schema.garminconnect_gear_id = "g2"
        schema.hide_hr = False

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.start_time is None
        assert result.end_time is None
        assert result.city is None
        assert result.town is None
        assert result.country is None
        assert result.gear_id is None
        assert result.strava_gear_id is None
        assert result.garminconnect_gear_id is None

    def test_non_owner_does_not_mask_visible_fields(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.hide_start_time = False
        schema.start_time = "2024-01-15T08:00:00"
        schema.hide_location = False
        schema.city = "City"
        schema.hide_gear = False
        schema.gear_id = 1

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.start_time == "2024-01-15T08:00:00"
        assert result.city == "City"
        assert result.gear_id == 1

    def test_mask_private_notes_false_allows_notes(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "visible"

        result = apply_visibility_mask(schema, is_owner=False, mask_private_notes=False)

        assert result.private_notes == "visible"

    def test_non_owner_masks_thumbnail_when_hide_map(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.hide_map = True
        schema.map_thumbnail_path = "42.webp"

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.map_thumbnail_path is None

    def test_non_owner_keeps_thumbnail_when_not_hide_map(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.hide_map = False
        schema.map_thumbnail_path = "42.webp"

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.map_thumbnail_path == "42.webp"

    def test_owner_keeps_thumbnail_even_with_hide_map(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.hide_map = True
        schema.map_thumbnail_path = "42.webp"

        result = apply_visibility_mask(schema, is_owner=True)

        assert result.map_thumbnail_path == "42.webp"

    def test_hide_start_time_clears_both_timestamps(self):
        from modules.activities.activity.schema import ActivityRead
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = ActivityRead(
            id=1,
            distance=1000,
            name="Ride",
            activity_type=5,
            start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
            hide_start_time=True,
        )

        apply_visibility_mask(schema, is_owner=False)

        assert schema.start_time is None
        assert schema.end_time is None

    @pytest.mark.parametrize(
        ("flag", "fields"),
        [
            ("hide_hr", ["average_hr", "max_hr"]),
            ("hide_power", ["average_power", "max_power", "normalized_power"]),
            ("hide_cadence", ["average_cad", "max_cad"]),
            ("hide_speed", ["average_speed", "max_speed"]),
            ("hide_pace", ["pace"]),
            ("hide_elevation", ["elevation_gain", "elevation_loss"]),
        ],
    )
    def test_metric_flags_mask_their_fields_for_non_owner(self, flag, fields):
        from modules.activities.activity.schema import ActivityRead
        from modules.activities.activity.serializers import apply_visibility_mask

        values = dict.fromkeys(fields, 10)
        schema = ActivityRead(id=1, distance=1000, name="Ride", activity_type=5, **values, **{flag: True})

        apply_visibility_mask(schema, is_owner=False)

        assert all(getattr(schema, field) is None for field in fields)

    def test_metric_fields_kept_when_flag_unset_or_owner(self):
        from modules.activities.activity.schema import ActivityRead
        from modules.activities.activity.serializers import apply_visibility_mask

        non_owner = ActivityRead(id=1, distance=1000, name="Ride", activity_type=5, average_hr=150, average_power=200)
        owner = ActivityRead(id=1, distance=1000, name="Ride", activity_type=5, average_hr=150, hide_hr=True)

        apply_visibility_mask(non_owner, is_owner=False)
        apply_visibility_mask(owner, is_owner=True)

        assert non_owner.average_hr == 150
        assert non_owner.average_power == 200
        assert owner.average_hr == 150

    def test_owner_keeps_everything(self):
        from modules.activities.activity.schema import ActivityRead
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = ActivityRead(
            id=1,
            distance=1000,
            name="Ride",
            activity_type=5,
            start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
            hide_start_time=True,
        )

        apply_visibility_mask(schema, is_owner=True)

        assert schema.start_time == datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)


class TestThumbnailKeyIsServerSide:
    def test_the_stored_key_is_never_serialized(self):
        from modules.activities.activity.schema import ActivityRead

        activity = ActivityRead(id=1, distance=0, name="Run", activity_type=1, map_thumbnail_path="1.webp")

        assert activity.map_thumbnail_path == "1.webp"
        assert "map_thumbnail_path" not in activity.model_dump()
