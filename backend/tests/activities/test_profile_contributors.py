"""Tests for package-owned activity profile contributors."""

import uuid
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_exercise_titles.integration_service as activity_exercise_titles_integration
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.activities.activity_sets.integration_service as activity_sets_integration
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.activity_workout_steps.integration_service as activity_workout_steps_integration

_NEW_ID = uuid.UUID(int=10)
_OLD_ID = str(uuid.UUID(int=1))
_OTHER_ID = str(uuid.UUID(int=2))


def _new_activity() -> activity_schema.ActivityRead:
    """Build a restored parent activity for contributor tests."""
    return activity_schema.ActivityRead(id=_NEW_ID, user_id=1, distance=0, name="Restored", activity_type=1)


@pytest.mark.parametrize(
    ("integration", "store_name", "record", "uses_parent_schema"),
    [
        (
            activity_laps_integration,
            "_store_laps",
            {"id": str(uuid.UUID(int=11)), "activity_id": _OLD_ID, "start_time": "2024-01-01T00:00:00Z"},
            False,
        ),
        (
            activity_sets_integration,
            "_store_sets",
            {
                "id": str(uuid.UUID(int=12)),
                "activity_id": _OLD_ID,
                "duration": 30.0,
                "set_type": "active",
                "start_time": "2024-01-01T00:00:00Z",
            },
            False,
        ),
        (
            activity_streams_integration,
            "_store_streams",
            {
                "id": str(uuid.UUID(int=13)),
                "activity_id": _OLD_ID,
                "stream_type": 1,
                "stream_waypoints": [{"hr": 140}],
            },
            True,
        ),
        (
            activity_workout_steps_integration,
            "_store_workout_steps",
            {
                "id": str(uuid.UUID(int=14)),
                "activity_id": _OLD_ID,
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
    source_records = [record, {**record, "id": str(uuid.UUID(int=99)), "activity_id": _OTHER_ID}]
    original_records = deepcopy(source_records)
    activity = _new_activity()
    db = MagicMock()

    with patch.object(integration, store_name) as store:
        restored = integration.profile_contributor().restore(source_records, _OLD_ID, activity, db)

    assert restored == 1
    assert source_records == original_records
    stored_record = store.call_args.args[0][0]
    stored_data = stored_record if isinstance(stored_record, dict) else stored_record.model_dump()
    if integration in (activity_laps_integration, activity_workout_steps_integration):
        assert "activity_id" not in stored_data
    else:
        assert stored_data["activity_id"] == _NEW_ID
    assert store.call_args.args[1] is activity if uses_parent_schema else store.call_args.args[1] == _NEW_ID
    assert store.call_args.args[2] is db


def test_media_profile_contributor_rekeys_without_mutating_source() -> None:
    """Media restore validates a flat key and leaves archive data untouched."""
    records = [
        {"id": str(uuid.UUID(int=15)), "activity_id": _OLD_ID, "media_path": f"{_OLD_ID}_photo.jpg", "media_type": 1}
    ]
    original_records = deepcopy(records)
    activity = _new_activity()
    db = MagicMock()

    with patch.object(activity_media_integration, "_restore_media_records") as store:
        restored = activity_media_integration.profile_contributor().restore(records, _OLD_ID, activity, db)

    assert restored == 1
    assert records == original_records
    assert store.call_args.args[0][0].media_path == f"{_NEW_ID}_photo.jpg"
    store.assert_called_once()


def test_global_profile_contributor_restores_valid_titles_once() -> None:
    """Global title restore removes ids and skips malformed archive records."""
    records: list[Any] = [
        {"id": str(uuid.UUID(int=20)), "exercise_category": 1, "exercise_name": 2, "wkt_step_name": "Press"},
        {"id": str(uuid.UUID(int=21)), "exercise_category": 1},
        "not-an-object",
    ]
    original_records = deepcopy(records)
    db = MagicMock()

    with patch.object(
        activity_exercise_titles_integration.activity_exercise_titles_crud, "create_activity_exercise_titles"
    ) as store:
        restored = activity_exercise_titles_integration.profile_global_contributor().restore(records, db)

    assert restored == 1
    assert records == original_records
    restored_title = store.call_args.args[0][0]
    assert not hasattr(restored_title, "id")
    assert restored_title.wkt_step_name == "Press"
    store.assert_called_once()
