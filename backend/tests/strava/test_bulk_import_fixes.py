"""Strava bulk import: gear names with a plus resolve, and an unreadable date does not drop the activity."""

from datetime import UTC, datetime
from unittest.mock import Mock

import modules.strava.bulk_import_service as strava_bulk


def _row(**overrides):
    return {
        "Activity Name": "Run",
        "Activity Description": "",
        "Activity Type": "Run",
        "Activity Date": "Oct 21, 2023, 8:13:28 AM",
        "Activity Gear": "",
        "Activity ID": "1",
        **overrides,
    }


def _metadata(row, gear=None):
    return strava_bulk.build_metadata_dict("a.fit", {"a.fit": row}, "2026-01-01T00:00:00", gear)


def test_a_gear_name_with_a_plus_resolves_to_the_users_gear():
    metadata = _metadata(_row(**{"Activity Gear": "Nike+Pegasus"}), {"Nike Pegasus": [4]})

    assert metadata["gear_id"] == 4


def test_gear_the_user_does_not_have_leaves_the_activity_without_gear():
    assert _metadata(_row(**{"Activity Gear": "Unknown"}), {"Nike Pegasus": [4]})["gear_id"] is None


def test_a_user_without_gear_does_not_crash_the_import():
    assert _metadata(_row(**{"Activity Gear": "Nike"}), None)["gear_id"] is None


def test_an_activity_without_gear_resolves_to_none():
    assert _metadata(_row(), {"Nike": [1]})["gear_id"] is None


def test_an_unreadable_start_date_imports_the_activity_rather_than_dropping_it():
    source = strava_bulk.StravaBulkImportSource(
        import_initiated_time="2026-01-01T00:00:00", user_id=1, strava_activities={"a.fit": _row()}
    )
    activity = Mock(start_time=datetime(2023, 10, 21, 7, 41, 47, tzinfo=UTC))

    assert (
        source.should_import(
            activity,
            {"metadata_found_in_csv": True, "activity date": "21 oct. 2023 à 08:13:28"},
            activities_in_file=5,
        )
        is True
    )


def test_a_multi_activity_file_still_skips_listings_that_do_not_match():
    source = strava_bulk.StravaBulkImportSource(
        import_initiated_time="2026-01-01T00:00:00", user_id=1, strava_activities={"a.fit": _row()}
    )
    activity = Mock(start_time=datetime(2023, 10, 21, 7, 41, 47, tzinfo=UTC))

    assert (
        source.should_import(
            activity,
            {"metadata_found_in_csv": True, "activity date": "Oct 21, 2023, 8:13:28 AM"},
            activities_in_file=5,
        )
        is False
    )
