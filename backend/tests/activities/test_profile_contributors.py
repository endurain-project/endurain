"""Tests for package-owned activity profile contributors, restored into a real activity on PostgreSQL."""

import uuid
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from sqlalchemy.orm import Session

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_exercise_titles.integration_service as activity_exercise_titles_integration
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.integration_service as activity_sets_integration
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.integration_service as activity_workout_steps_integration
from tests._factories import activities as activity_factory
from tests._factories import users as user_factory

_OLD_ID = uuid.UUID(int=1)
_OTHER_ID = uuid.UUID(int=2)


def _new_activity(db: Session) -> activity_schema.ActivityRead:
    """Stage the restored parent activity the contributors restore onto."""
    return activity_factory.make_activity(db, user_factory.make_user(db).id, name="Restored")


def _stored_laps(db: Session, activity_id: uuid.UUID) -> list[Any]:
    return activity_laps_crud.get_activity_laps(activity_id, db)


def _stored_sets(db: Session, activity_id: uuid.UUID) -> list[Any]:
    return activity_sets_crud.get_activity_sets(activity_id, db)


def _stored_streams(db: Session, activity_id: uuid.UUID) -> list[Any]:
    return activity_streams_crud.get_activity_streams(activity_id, db)


def _stored_workout_steps(db: Session, activity_id: uuid.UUID) -> list[Any]:
    return activity_workout_steps_crud.get_activity_workout_steps(activity_id, db)


@pytest.mark.parametrize(
    ("integration", "read_rows", "record"),
    [
        pytest.param(
            activity_laps_integration,
            _stored_laps,
            {"id": str(uuid.UUID(int=11)), "activity_id": str(_OLD_ID), "start_time": "2024-01-01T00:00:00Z"},
            id="laps",
        ),
        pytest.param(
            activity_sets_integration,
            _stored_sets,
            {
                "id": str(uuid.UUID(int=12)),
                "activity_id": str(_OLD_ID),
                "duration": 30.0,
                "set_type": "active",
                "start_time": "2024-01-01T00:00:00Z",
            },
            id="sets",
        ),
        pytest.param(
            activity_streams_integration,
            _stored_streams,
            {
                "id": str(uuid.UUID(int=13)),
                "activity_id": str(_OLD_ID),
                "stream_type": 1,
                "stream_waypoints": [{"hr": 140}],
            },
            id="streams",
        ),
        pytest.param(
            activity_workout_steps_integration,
            _stored_workout_steps,
            {
                "id": str(uuid.UUID(int=14)),
                "activity_id": str(_OLD_ID),
                "message_index": 0,
                "duration_type": "time",
            },
            id="workout-steps",
        ),
    ],
)
def test_activity_profile_contributor_filters_copies_and_rekeys(
    db: Session,
    integration: Any,
    read_rows: Callable[[Session, uuid.UUID], list[Any]],
    record: dict[str, Any],
) -> None:
    """Each JSON contributor restores only its activity's record, onto the new activity, under a new id."""
    source_records = [record, {**record, "id": str(uuid.UUID(int=99)), "activity_id": str(_OTHER_ID)}]
    original_records = deepcopy(source_records)
    activity = _new_activity(db)

    restored = integration.profile_contributor().restore(source_records, _OLD_ID, activity, db)
    db.flush()

    assert restored == 1
    assert source_records == original_records
    (row,) = read_rows(db, activity.id)
    assert row.activity_id == activity.id
    assert row.id != uuid.UUID(record["id"])
    # The record exported under another activity went nowhere, not onto the new one and not onto the old id.
    assert read_rows(db, _OLD_ID) == []
    assert read_rows(db, _OTHER_ID) == []


def test_media_profile_contributor_rekeys_without_mutating_source(db: Session) -> None:
    """Media restore validates a flat key, stores it under the new activity and leaves archive data untouched."""
    records = [
        {
            "id": str(uuid.UUID(int=15)),
            "activity_id": str(_OLD_ID),
            "media_path": f"{_OLD_ID}_photo.jpg",
            "media_type": 1,
        }
    ]
    original_records = deepcopy(records)
    activity = _new_activity(db)

    restored = activity_media_integration.profile_contributor().restore(records, _OLD_ID, activity, db)
    db.flush()

    assert restored == 1
    assert records == original_records
    (media,) = activity_media_crud.get_media_for_activity(activity.id, db)
    assert media.activity_id == activity.id
    assert media.media_path == f"{activity.id}_photo.jpg"
    assert media.id != uuid.UUID(int=15)
    assert activity_media_crud.get_media_for_activity(_OLD_ID, db) == []


def test_global_profile_contributor_restores_valid_titles_once(db: Session) -> None:
    """Global title restore removes ids and skips malformed archive records."""
    records: list[Any] = [
        {"id": 987654, "exercise_category": 1, "exercise_name": 2, "wkt_step_name": "Press"},
        {"id": 987655, "exercise_category": 1},
        "not-an-object",
    ]
    original_records = deepcopy(records)

    restored = activity_exercise_titles_integration.profile_global_contributor().restore(records, db)
    db.flush()

    assert restored == 1
    assert records == original_records
    stored = activity_exercise_titles_crud.get_activity_exercise_titles(db)
    assert [(t.exercise_category, t.exercise_name, t.wkt_step_name) for t in stored] == [(1, 2, "Press")]
    assert all(t.id not in (987654, 987655) for t in stored)
