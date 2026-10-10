"""Tests for the activity-type constants and mapping helpers.

Relocated from ``tests/activities/activity/test_utils*`` when the activity-type
mapping helpers moved into ``activity/constants.py`` (co-located with the maps).
"""

from modules.activities.activity.constants import (
    ACTIVITY_ID_TO_NAME,
    ACTIVITY_NAME_TO_ID,
    define_activity_type,
    set_activity_name_based_on_activity_type,
)


class TestDefineActivityType:
    def test_known_type_returns_id(self):
        assert define_activity_type("Run") == 1
        assert define_activity_type("run") == 1
        assert define_activity_type("Ride") == 4
        assert define_activity_type("Walk") == 11

    def test_known_alias_returns_id(self):
        assert define_activity_type("Cycling") == 4
        assert define_activity_type("Swim") == 8
        assert define_activity_type("Trail") == 2

    def test_unknown_type_returns_default(self):
        assert define_activity_type("Skydiving") == 10

    def test_non_string_input_returns_default(self):
        assert define_activity_type(123) == 10
        assert define_activity_type(None) == 10


class TestSetActivityNameBasedOnActivityType:
    def test_known_type_returns_name_with_workout_suffix(self):
        assert set_activity_name_based_on_activity_type(1) == "Run workout"
        assert set_activity_name_based_on_activity_type(4) == "Ride workout"

    def test_workout_type_returns_workout(self):
        assert set_activity_name_based_on_activity_type(10) == "Workout"

    def test_unknown_type_returns_workout(self):
        assert set_activity_name_based_on_activity_type(999) == "Workout"


class TestActivityIdToName:
    def test_mapping_contains_common_types(self):
        assert ACTIVITY_ID_TO_NAME[1] == "Run"
        assert ACTIVITY_ID_TO_NAME[4] == "Ride"
        assert ACTIVITY_ID_TO_NAME[11] == "Walk"
        assert ACTIVITY_ID_TO_NAME[19] == "Strength training"
        assert ACTIVITY_ID_TO_NAME[47] == "Jump rope"

    def test_unknown_id(self):
        assert 999 not in ACTIVITY_ID_TO_NAME


class TestActivityNameToId:
    def test_contains_known_mappings(self):
        assert ACTIVITY_NAME_TO_ID["running"] == 1
        assert ACTIVITY_NAME_TO_ID["cycling"] == 4
        assert ACTIVITY_NAME_TO_ID["swim"] == 8
        assert ACTIVITY_NAME_TO_ID["hike"] == 12
        assert ACTIVITY_NAME_TO_ID["yoga"] == 14
        assert ACTIVITY_NAME_TO_ID["strength_training"] == 19
        assert ACTIVITY_NAME_TO_ID["hiit"] == 46
        assert ACTIVITY_NAME_TO_ID["jump_rope"] == 47
        assert ACTIVITY_NAME_TO_ID["jumprope"] == 47
        assert ACTIVITY_NAME_TO_ID["indoor_running"] == 40

    def test_unknown_name_not_in_mapping(self):
        assert "skydiving" not in ACTIVITY_NAME_TO_ID
