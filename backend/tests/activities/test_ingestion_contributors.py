"""Tests that each ingestion contributor checks the parsed payload it is handed."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_exercise_titles.integration_service as activity_exercise_titles_integration
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.integration_service as activity_sets_integration
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.activity_workout_steps.integration_service as activity_workout_steps_integration

_ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-00000000000a")


def _activity() -> activity_schema.ActivityRead:
    return activity_schema.ActivityRead(id=_ACTIVITY_ID, user_id=1, distance=0, name="Parsed", activity_type=1)


_SET = activity_sets_contracts.ActivitySetsCreate(
    activity_id=_ACTIVITY_ID, duration=30.0, set_type="active", start_time="2024-01-01T00:00:00Z"
)
_STEP = activity_workout_steps_contracts.ActivityWorkoutStepsCreate(message_index=0, duration_type="time")
_STREAM = activity_streams_contracts.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 140}])

_ACTIVITY_CONTRIBUTORS = [
    pytest.param(activity_laps_integration, "_store_laps", [{"start_time": "2024-01-01T00:00:00Z"}], id="laps"),
    pytest.param(activity_sets_integration, "_store_sets", [_SET, [30.0, 1, None, "active"]], id="sets"),
    pytest.param(activity_workout_steps_integration, "_store_workout_steps", [_STEP], id="workout-steps"),
    pytest.param(activity_streams_integration, "_store_streams", [_STREAM], id="streams"),
]


class TestActivityComponents:
    @pytest.mark.parametrize(("integration", "store_name", "payload"), _ACTIVITY_CONTRIBUTORS)
    def test_a_payload_of_the_childs_shape_is_stored(self, integration, store_name, payload):
        with patch.object(integration, store_name) as store:
            integration.ingestion_contributor().persist(payload, _activity(), MagicMock())

        store.assert_called_once()

    @pytest.mark.parametrize(("integration", "store_name", "payload"), _ACTIVITY_CONTRIBUTORS)
    def test_a_payload_of_another_shape_is_refused_before_anything_is_stored(self, integration, store_name, payload):
        with patch.object(integration, store_name) as store, pytest.raises(ValidationError):
            integration.ingestion_contributor().persist(["not a row"], _activity(), MagicMock())

        store.assert_not_called()


class TestFileComponents:
    def test_exercise_titles_are_stored(self):
        title = activity_exercise_titles_contracts.ActivityExerciseTitlesCreate(
            exercise_category=1, exercise_name=2, wkt_step_name="Squat"
        )
        with patch.object(
            activity_exercise_titles_integration.activity_exercise_titles_crud, "create_activity_exercise_titles"
        ) as create:
            activity_exercise_titles_integration.ingestion_contributor().persist([title], MagicMock())

        assert create.call_args.args[0] == [title]

    def test_a_payload_of_another_shape_is_refused(self):
        with (
            patch.object(
                activity_exercise_titles_integration.activity_exercise_titles_crud, "create_activity_exercise_titles"
            ) as create,
            pytest.raises(ValidationError),
        ):
            activity_exercise_titles_integration.ingestion_contributor().persist(["not a title"], MagicMock())

        create.assert_not_called()
