"""Tests for package-owned activity profile contributors."""

from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_exercise_titles.integration_service as exercise_titles_integration
import modules.activities.activity_laps.integration_service as laps_integration
import modules.activities.activity_media.integration_service as media_integration
import modules.activities.activity_sets.integration_service as sets_integration
import modules.activities.activity_streams.integration_service as streams_integration
import modules.activities.activity_workout_steps.integration_service as workout_steps_integration


def _new_activity() -> activity_schema.Activity:
    """Build a restored parent activity for contributor tests."""
    return activity_schema.Activity(id=10, user_id=1, distance=0, name="Restored", activity_type=1)


@pytest.mark.parametrize(
    ("integration", "store_name", "record", "uses_parent_schema"),
    [
        (
            laps_integration,
            "_store_laps",
            {"id": 11, "activity_id": 1, "start_time": "2024-01-01T00:00:00Z"},
            False,
        ),
        (
            sets_integration,
            "_store_sets",
            {
                "id": 12,
                "activity_id": 1,
                "duration": 30.0,
                "set_type": "active",
                "start_time": "2024-01-01T00:00:00Z",
            },
            False,
        ),
        (
            streams_integration,
            "_store_streams",
            {
                "id": 13,
                "activity_id": 1,
                "stream_type": 1,
                "stream_waypoints": [{"hr": 140}],
            },
            True,
        ),
        (
            workout_steps_integration,
            "_store_workout_steps",
            {
                "id": 14,
                "activity_id": 1,
                "message_index": 0,
                "duration_type": "time",
            },
            False,
        ),
    ],
)
def test_activity_profile_contributor_filters_copies_and_rekeys(
    integration: Any,
    store_name: str,
    record: dict[str, Any],
    uses_parent_schema: bool,
) -> None:
    """Each JSON contributor owns filtering, validation, and parent re-keying."""
    source_records = [record, {**record, "id": 99, "activity_id": 2}]
    original_records = deepcopy(source_records)
    activity = _new_activity()
    db = MagicMock()

    with patch.object(integration, store_name) as store:
        restored = integration.profile_contributor().restore(source_records, 1, activity, db)

    assert restored == 1
    assert source_records == original_records
    stored_record = store.call_args.args[0][0]
    stored_data = stored_record if isinstance(stored_record, dict) else stored_record.model_dump()
    if integration is laps_integration:
        assert "activity_id" not in stored_data
    else:
        assert stored_data["activity_id"] == 10
    assert store.call_args.args[1] is activity if uses_parent_schema else store.call_args.args[1] == 10
    assert store.call_args.args[2] is db


def test_media_profile_contributor_rekeys_without_mutating_source() -> None:
    """Media restore validates a flat key and leaves archive data untouched."""
    records = [{"id": 15, "activity_id": 1, "media_path": "1_photo.jpg", "media_type": 1}]
    original_records = deepcopy(records)
    activity = _new_activity()
    db = MagicMock()

    with patch.object(media_integration, "_restore_media_records") as store:
        restored = media_integration.profile_contributor().restore(records, 1, activity, db)

    assert restored == 1
    assert records == original_records
    assert store.call_args.args[0][0].media_path == "10_photo.jpg"
    store.assert_called_once()


def test_global_profile_contributor_restores_valid_titles_once() -> None:
    """Global title restore removes ids and skips malformed archive records."""
    records: list[Any] = [
        {"id": 20, "exercise_category": 1, "exercise_name": 2, "wkt_step_name": "Press"},
        {"id": 21, "exercise_category": 1},
        "not-an-object",
    ]
    original_records = deepcopy(records)
    db = MagicMock()

    with patch.object(exercise_titles_integration, "_store_exercise_titles") as store:
        restored = exercise_titles_integration.profile_global_contributor().restore(records, db)

    assert restored == 1
    assert records == original_records
    restored_title = store.call_args.args[0][0]
    assert restored_title.id is None
    assert restored_title.wkt_step_name == "Press"
    store.assert_called_once()
