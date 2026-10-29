"""What the laps package declares itself to be.

The paginated read itself is asserted once, in
``tests/activities/activity/test_child_collection_service.py``. What remains
package-specific is the declaration: the wrong hide flag or the wrong CRUD pair
would silently serve — or refuse — the wrong rows — and the per-viewer mask, which
keeps a lap from serving what its activity hides.
"""

import dataclasses
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.service as service


class TestCollectionDeclaration:
    def test_it_is_guarded_by_the_right_parent_flag(self):
        assert service._COLLECTION.hide_attr == "hide_laps"

    def test_it_reads_through_its_own_crud(self):
        assert service._COLLECTION.fetch is activity_laps_crud.get_activity_laps
        assert service._COLLECTION.count is activity_laps_crud.count_activity_laps

    def test_it_builds_its_own_page_type(self):
        assert service._COLLECTION.build == activity_laps_schema.ActivityLapsPage.build


class TestDelegation:
    @patch("modules.activities.activity.child_collection_service.activity_child_access_service")
    def test_the_authenticated_read_goes_through_the_shared_gate(self, mock_gate):
        mock_gate.resolve_readable_parent.return_value = None
        db = MagicMock()

        page = service.list_activity_laps(5, 1, db)

        assert (page.items, page.total) == ([], 0)
        mock_gate.resolve_readable_parent.assert_called_once_with(5, 1, db)

    @patch("modules.activities.activity.child_collection_service.activity_child_access_service")
    def test_the_public_read_goes_through_the_public_gate(self, mock_gate):
        mock_gate.resolve_public_parent.return_value = None
        db = MagicMock()

        page = service.list_public_activity_laps(5, db)

        assert (page.items, page.total) == ([], 0)
        mock_gate.resolve_public_parent.assert_called_once_with(5, db)


_EVERY_FLAG = (
    "hide_start_time",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_speed",
    "hide_pace",
    "hide_elevation",
)


def _lap(**fields) -> activity_laps_schema.ActivityLapsRead:
    return activity_laps_schema.ActivityLapsRead(
        id=1,
        activity_id=5,
        start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
        start_position_lat=38.7,
        start_position_long=-9.1,
        end_position_lat=38.8,
        end_position_long=-9.2,
        total_distance=1000.0,
        total_elapsed_time=300.0,
        avg_heart_rate=150,
        max_heart_rate=170,
        avg_power=200,
        max_power=400,
        normalized_power=210,
        total_work=60000,
        avg_cadence=85,
        max_cadence=95,
        avg_fractional_cadence=0.5,
        max_fractional_cadence=0.5,
        total_cycles=420,
        enhanced_avg_speed=3.3,
        enhanced_max_speed=4.1,
        enhanced_avg_pace=0.3,
        enhanced_max_pace=0.24,
        total_ascent=12,
        total_descent=10,
        enhanced_min_altitude=40.0,
        enhanced_max_altitude=52.0,
        **fields,
    )


def _parent(**flags) -> SimpleNamespace:
    return SimpleNamespace(id=5, user_id=1, hide_laps=False, **dict.fromkeys(_EVERY_FLAG, False) | flags)


def _reading(*laps):
    """The laps collection as declared, reading the given rows instead of the database."""
    return dataclasses.replace(
        service._COLLECTION, fetch=MagicMock(return_value=list(laps)), count=MagicMock(return_value=len(laps))
    )


class TestViewerMask:
    """A lap repeats the activity's hideable data, so each field follows its parent flag."""

    def test_it_is_the_collections_mask(self):
        assert service._COLLECTION.mask is service._mask_for_viewer

    @pytest.mark.parametrize(
        ("flag", "fields"),
        [
            ("hide_start_time", ["start_time"]),
            ("hide_map", ["start_position_lat", "start_position_long", "end_position_lat", "end_position_long"]),
            ("hide_hr", ["avg_heart_rate", "max_heart_rate"]),
            ("hide_power", ["avg_power", "max_power", "normalized_power", "total_work"]),
            (
                "hide_cadence",
                ["avg_cadence", "max_cadence", "avg_fractional_cadence", "max_fractional_cadence", "total_cycles"],
            ),
            ("hide_speed", ["enhanced_avg_speed", "enhanced_max_speed"]),
            ("hide_pace", ["enhanced_avg_pace", "enhanced_max_pace"]),
            ("hide_elevation", ["total_ascent", "total_descent", "enhanced_min_altitude", "enhanced_max_altitude"]),
        ],
    )
    def test_each_flag_clears_its_fields_and_nothing_else(self, flag, fields):
        lap = _lap()

        [masked] = service._mask_for_viewer([lap], _parent(**{flag: True}))

        assert all(getattr(masked, field) is None for field in fields)
        untouched = set(activity_laps_schema.ActivityLapsRead.model_fields) - set(fields)
        assert all(getattr(masked, field) == getattr(lap, field) for field in untouched)

    def test_no_flag_leaves_the_laps_as_they_are(self):
        laps = [_lap()]

        assert service._mask_for_viewer(laps, _parent()) == laps

    def test_a_non_owner_reads_the_masked_laps(self):
        with patch.object(service, "_COLLECTION", _reading(_lap())):
            page = service.list_for_activity(_parent(hide_map=True, hide_hr=True), 2, MagicMock())

        assert (page.items[0].start_position_lat, page.items[0].avg_heart_rate) == (None, None)
        assert page.items[0].total_distance == 1000.0

    def test_the_owner_reads_the_laps_unmasked(self):
        with patch.object(service, "_COLLECTION", _reading(_lap())):
            page = service.list_for_activity(_parent(hide_map=True, hide_hr=True), 1, MagicMock())

        assert page.items == [_lap()]
