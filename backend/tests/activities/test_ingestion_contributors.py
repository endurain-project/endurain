"""Tests that each ingestion contributor stores the parsed payload it is handed, or refuses it, on PostgreSQL."""

from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_exercise_titles.integration_service as activity_exercise_titles_integration
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.integration_service as activity_sets_integration
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.integration_service as activity_workout_steps_integration
from tests._factories import activities as activity_factory
from tests._factories import users as user_factory


def _lap_start_times(db: Session, activity: activity_schema.ActivityRead) -> list[Any]:
    return [lap.start_time for lap in activity_laps_crud.get_activity_laps(activity.id, db)]


def _set_durations(db: Session, activity: activity_schema.ActivityRead) -> list[Any]:
    return [row.duration for row in activity_sets_crud.get_activity_sets(activity.id, db)]


def _step_duration_types(db: Session, activity: activity_schema.ActivityRead) -> list[Any]:
    return [step.duration_type for step in activity_workout_steps_crud.get_activity_workout_steps(activity.id, db)]


def _stream_waypoints(db: Session, activity: activity_schema.ActivityRead) -> list[Any]:
    return [stream.stream_waypoints for stream in activity_streams_crud.get_activity_streams(activity.id, db)]


_SET = activity_sets_contracts.ActivitySetsCreate(
    activity_id="00000000-0000-4000-8000-00000000000a",
    duration=30.0,
    set_type="active",
    start_time="2024-01-01T00:00:00Z",
)
_STEP = activity_workout_steps_contracts.ActivityWorkoutStepsCreate(message_index=0, duration_type="time")
_STREAM = activity_streams_contracts.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 140}])

# (integration, payload, expected rows read back, how to read them)
_ACTIVITY_CONTRIBUTORS = [
    pytest.param(
        activity_laps_integration,
        [{"start_time": "2024-01-01T00:00:00Z"}],
        1,
        _lap_start_times,
        id="laps",
    ),
    pytest.param(activity_sets_integration, [_SET], 1, _set_durations, id="sets"),
    pytest.param(activity_workout_steps_integration, [_STEP], 1, _step_duration_types, id="workout-steps"),
    pytest.param(activity_streams_integration, [_STREAM], 1, _stream_waypoints, id="streams"),
]


class TestActivityComponents:
    @pytest.mark.parametrize(("integration", "payload", "expected_rows", "read_rows"), _ACTIVITY_CONTRIBUTORS)
    def test_a_payload_of_the_childs_shape_is_stored_against_the_activity(
        self, db: Session, integration, payload, expected_rows, read_rows
    ):
        activity = activity_factory.make_activity(db, user_factory.make_user(db).id)

        integration.ingestion_contributor().persist(payload, activity, db)
        db.flush()

        assert len(read_rows(db, activity)) == expected_rows

    @pytest.mark.parametrize(("integration", "payload", "expected_rows", "read_rows"), _ACTIVITY_CONTRIBUTORS)
    def test_a_payload_of_another_shape_is_refused_before_anything_is_stored(
        self, db: Session, integration, payload, expected_rows, read_rows
    ):
        activity = activity_factory.make_activity(db, user_factory.make_user(db).id)

        with pytest.raises(ValidationError):
            integration.ingestion_contributor().persist(["not a row"], activity, db)
        db.flush()

        assert read_rows(db, activity) == []

    def test_the_stored_fields_are_the_payloads(self, db: Session):
        activity = activity_factory.make_activity(db, user_factory.make_user(db).id)

        activity_laps_integration.ingestion_contributor().persist(
            [{"start_time": "2024-01-01T00:00:00Z"}], activity, db
        )
        activity_sets_integration.ingestion_contributor().persist([_SET], activity, db)
        activity_workout_steps_integration.ingestion_contributor().persist([_STEP], activity, db)
        activity_streams_integration.ingestion_contributor().persist([_STREAM], activity, db)
        db.flush()

        (lap,) = activity_laps_crud.get_activity_laps(activity.id, db)
        (stored_set,) = activity_sets_crud.get_activity_sets(activity.id, db)
        (step,) = activity_workout_steps_crud.get_activity_workout_steps(activity.id, db)
        (stream,) = activity_streams_crud.get_activity_streams(activity.id, db)
        assert lap.start_time is not None and lap.start_time.year == 2024
        assert (stored_set.activity_id, stored_set.duration, stored_set.set_type) == (activity.id, 30.0, "active")
        assert (step.activity_id, step.message_index, step.duration_type) == (activity.id, 0, "time")
        assert (stream.activity_id, stream.stream_type, stream.stream_waypoints) == (activity.id, 1, [{"hr": 140}])

    def test_sets_are_stored_from_the_raw_rows_the_fit_parser_emits(self, db: Session):
        activity = activity_factory.make_activity(db, user_factory.make_user(db).id)

        raw_row = [45.0, 8, 20.0, "active", "2024-01-01T00:01:00Z", None, None]

        activity_sets_integration.ingestion_contributor().persist([_SET, raw_row], activity, db)
        db.flush()

        stored = activity_sets_crud.get_activity_sets(activity.id, db)
        assert sorted((row.duration, row.repetitions, row.weight) for row in stored) == [
            (30.0, None, None),
            (45.0, 8, 20.0),
        ]


class TestFileComponents:
    def test_exercise_titles_are_stored(self, db: Session):
        title = activity_exercise_titles_contracts.ActivityExerciseTitlesCreate(
            exercise_category=1, exercise_name=2, wkt_step_name="Squat"
        )

        activity_exercise_titles_integration.ingestion_contributor().persist([title], db)
        db.flush()

        stored = activity_exercise_titles_crud.get_activity_exercise_titles(db)
        assert [(t.exercise_category, t.exercise_name, t.wkt_step_name) for t in stored] == [(1, 2, "Squat")]

    def test_a_payload_of_another_shape_is_refused(self, db: Session):
        with pytest.raises(ValidationError):
            activity_exercise_titles_integration.ingestion_contributor().persist(["not a title"], db)
        db.flush()

        assert activity_exercise_titles_crud.get_activity_exercise_titles(db) == []
