"""Tests for activity schema validators."""

import pytest
from pydantic import ValidationError

import modules.activities.activity.schema as activity_schema
from modules.activities.activity.constants import ActivityType

_ROW = {"distance": 0, "name": "Run", "activity_type": 1}


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
        assert activity_schema.ActivityEdit(visibility="followers").model_fields_set == {"visibility"}


class TestBodyIdsFitIntegerColumns:
    """A client-supplied id above the int4 range would reach PostgreSQL and answer 500."""

    def test_edit_rejects_an_id_above_int32(self):
        with pytest.raises(ValidationError):
            activity_schema.ActivityEdit(gear_id=2**31)

    def test_edit_accepts_the_largest_gear_id(self):
        assert activity_schema.ActivityEdit(gear_id=2**31 - 1).gear_id == 2**31 - 1

    def test_base_rejects_a_gear_id_above_int32(self):
        with pytest.raises(ValidationError):
            activity_schema.ActivityBase(distance=0, name="Run", activity_type=1, gear_id=2**31)


class TestActivityTypeVocabulary:
    """An activity type is one of the keys the application knows, never the stored integer."""

    def test_edit_rejects_an_unknown_type(self):
        with pytest.raises(ValidationError):
            activity_schema.ActivityEdit(activity_type="curling")

    @pytest.mark.parametrize("activity_type", [ActivityType.RUN, ActivityType.JUMP_ROPE])
    def test_edit_accepts_a_known_type(self, activity_type):
        assert activity_schema.ActivityEdit(activity_type=activity_type.value).activity_type is activity_type

    @pytest.mark.parametrize("stored", [1, "1"])
    def test_edit_rejects_the_stored_integer(self, stored):
        with pytest.raises(ValidationError):
            activity_schema.ActivityEdit(activity_type=stored)

    def test_a_stored_row_reads_as_the_key(self):
        assert activity_schema.ActivityBase.model_validate({**_ROW, "activity_type": 2}).activity_type == "trail_run"

    def test_every_type_has_a_unique_key_and_stored_id(self):
        assert len({t.value for t in ActivityType}) == len({t.stored for t in ActivityType}) == len(ActivityType)


class TestActivityEditName:
    """A client-sent activity name is not blank and carries no text direction control."""

    @pytest.mark.parametrize("name", ["   ", "\t", "Morning ‮nur gninrom", "a⁦b", "a‏b"])
    def test_a_blank_or_directional_name_is_refused(self, name):
        with pytest.raises(ValidationError):
            activity_schema.ActivityEdit(name=name)

    @pytest.mark.parametrize("name", ["Morning run", "می‌خواهم", "👨‍👩‍👧"])
    def test_an_ordinary_name_is_kept(self, name):
        assert activity_schema.ActivityEdit(name=name).name == name
