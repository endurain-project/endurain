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
            "name",
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
        edit = activity_schema.ActivityEdit(description=None, private_notes=None, gear_id=None)

        assert edit.model_fields_set == {"description", "private_notes", "gear_id"}

    def test_omitted_fields_are_not_set(self):
        assert activity_schema.ActivityEdit(visibility=1).model_fields_set == {"visibility"}


class TestBodyIdsFitIntegerColumns:
    """A client-supplied id above the int4 range would reach PostgreSQL and answer 500."""

    @pytest.mark.parametrize("field", ["gear_id", "activity_type"])
    def test_edit_rejects_an_id_above_int32(self, field):
        with pytest.raises(ValidationError):
            activity_schema.ActivityEdit(**{field: 2**31})

    def test_edit_accepts_the_largest_gear_id(self):
        assert activity_schema.ActivityEdit(gear_id=2**31 - 1).gear_id == 2**31 - 1

    def test_base_rejects_a_gear_id_above_int32(self):
        with pytest.raises(ValidationError):
            activity_schema.ActivityBase(distance=0, name="Run", activity_type=1, gear_id=2**31)


class TestActivityTypeVocabulary:
    """An activity type must be one of the ids the application knows."""

    def test_edit_rejects_an_unknown_type(self):
        with pytest.raises(ValidationError, match="Unknown activity type"):
            activity_schema.ActivityEdit(activity_type=9999)

    @pytest.mark.parametrize("activity_type", [1, 47])
    def test_edit_accepts_a_known_type(self, activity_type):
        assert activity_schema.ActivityEdit(activity_type=activity_type).activity_type == activity_type

    def test_edit_rejects_a_numeric_string(self):
        with pytest.raises(ValidationError):
            activity_schema.ActivityEdit(activity_type="1")
