"""Tests for activity schema validators."""

import pytest
from pydantic import ValidationError

import modules.activities.activity.schema as activity_schema


class TestTimezoneCanonicalization:
    """Legacy timezone aliases are stored under their canonical name."""

    def _activity(self, timezone):
        return activity_schema.ActivityBase(distance=0, name="Run", activity_type=1, timezone=timezone)

    def test_legacy_alias_is_canonicalized(self):
        assert self._activity("GB-Eire").timezone == "Europe/London"

    def test_canonical_name_is_kept(self):
        assert self._activity("Europe/Lisbon").timezone == "Europe/Lisbon"

    def test_none_is_kept(self):
        assert self._activity(None).timezone is None


class TestActivityEditNotNullColumns:
    """A field whose column is NOT NULL may be omitted from an edit but not cleared."""

    @pytest.mark.parametrize(
        "field",
        [
            "activity_type",
            "visibility",
            "is_hidden",
            "hide_start_time",
            "hide_location",
            "hide_map",
            "hide_hr",
            "hide_power",
            "hide_cadence",
            "hide_elevation",
            "hide_speed",
            "hide_pace",
            "hide_laps",
            "hide_workout_sets_steps",
            "hide_gear",
        ],
    )
    def test_an_explicit_null_is_rejected(self, field):
        with pytest.raises(ValidationError, match=f"{field} cannot be null"):
            activity_schema.ActivityEdit(**{field: None})

    def test_nullable_fields_can_still_be_cleared(self):
        edit = activity_schema.ActivityEdit(name=None, description=None, private_notes=None, gear_id=None)

        assert edit.model_fields_set == {"name", "description", "private_notes", "gear_id"}

    def test_omitted_fields_are_not_set(self):
        assert activity_schema.ActivityEdit(visibility=1).model_fields_set == {"visibility"}
