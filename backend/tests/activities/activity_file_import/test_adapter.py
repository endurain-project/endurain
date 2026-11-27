"""Tests for the activity_file_import adapter (parser dict -> ParsedActivity).

Moved from ``tests/activities/activity/test_utils.py`` when ``parse_activity_streams_from_file``
was replaced by :func:`~modules.activities.activity_file_import.adapter.parsed_info_to_parsed_activity`.
The adapter hands the samples assembly built over as the ``samples`` component; the activity id is assigned
later by ``ingestion_service.store_parsed_activity``.
"""

import uuid

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.contracts as activity_streams_contracts
from modules.activities.activity_file_import.adapter import parsed_info_to_parsed_activity


def _activity() -> activity_schema.ActivityRead:
    """A minimal valid Activity (the ingestion contract's activity type)."""
    return activity_schema.ActivityRead(
        id=uuid.UUID("11111111-1111-4111-8111-111111111111"), distance=0, name="test", activity_type=1
    )


class TestParsedInfoToParsedActivity:
    def test_the_samples_are_the_samples_component_and_no_old_streams_are_built(self):
        samples = activity_streams_contracts.ParsedSamples(offsets_ms=[0, 1000], heart_rate=[145.0, 146.0])

        result = parsed_info_to_parsed_activity({"activity": _activity(), "samples": samples})

        assert result.components["samples"] is samples
        assert "streams" not in result.components

    def test_a_session_without_samples_has_none(self):
        result = parsed_info_to_parsed_activity({"activity": _activity(), "samples": None})

        assert result.components["samples"] is None

    def test_carries_activity_and_children(self):
        activity = _activity()
        parsed_info = {
            "activity": activity,
            "laps": [{"lap": 1}],
            "sets": [{"set": 1}],
            "workout_steps": [{"step": 1}],
        }

        result = parsed_info_to_parsed_activity(parsed_info)

        assert result.activity is activity
        assert result.components == {
            "samples": None,
            "laps": [{"lap": 1}],
            "sets": [{"set": 1}],
            "workout_steps": [{"step": 1}],
        }
