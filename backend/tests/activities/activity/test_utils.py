from unittest.mock import MagicMock

import pytest


class TestEscapeLike:
    def test_escape_percent(self):
        from modules.activities.activity.crud import escape_like

        result = escape_like("100%")
        assert result == "100\\%"

    def test_escape_underscore(self):
        from modules.activities.activity.crud import escape_like

        result = escape_like("test_name")
        assert result == "test\\_name"

    def test_escape_backslash(self):
        from modules.activities.activity.crud import escape_like

        result = escape_like("foo\\bar")
        assert result == "foo\\\\bar"

    def test_no_escaping_needed(self):
        from modules.activities.activity.crud import escape_like

        result = escape_like("hello")
        assert result == "hello"

    def test_escape_all(self):
        from modules.activities.activity.crud import escape_like

        result = escape_like("a%b_c\\d")
        assert result == "a\\%b\\_c\\\\d"


class TestApplyVisibilityMask:
    def test_owner_no_mask(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "secret"
        schema.hide_start_time = True
        schema.hide_location = True
        schema.hide_gear = True

        result = apply_visibility_mask(schema, is_owner=True)

        assert result.private_notes == "secret"

    def test_non_owner_masks_private_notes(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "secret"

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.private_notes is None

    def test_non_owner_masks_hidden_fields(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.hide_start_time = True
        schema.start_time = "2024-01-15T08:00:00"
        schema.end_time = "2024-01-15T09:00:00"
        schema.hide_location = True
        schema.city = "City"
        schema.town = "Town"
        schema.country = "Country"
        schema.hide_gear = True
        schema.gear_id = 1
        schema.strava_gear_id = "g1"
        schema.garminconnect_gear_id = "g2"
        schema.hide_hr = False

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.start_time is None
        assert result.end_time is None
        assert result.city is None
        assert result.town is None
        assert result.country is None
        assert result.gear_id is None
        assert result.strava_gear_id is None
        assert result.garminconnect_gear_id is None

    def test_non_owner_does_not_mask_visible_fields(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.hide_start_time = False
        schema.start_time = "2024-01-15T08:00:00"
        schema.hide_location = False
        schema.city = "City"
        schema.hide_gear = False
        schema.gear_id = 1

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.start_time == "2024-01-15T08:00:00"
        assert result.city == "City"
        assert result.gear_id == 1

    def test_mask_private_notes_false_allows_notes(self):
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "visible"

        result = apply_visibility_mask(schema, is_owner=False, mask_private_notes=False)

        assert result.private_notes == "visible"


class TestCalculateActivityStats:
    def test_calculate_stats(self):
        from modules.activities.activity.stats import calculate_activity_stats

        activity = MagicMock()
        activity.activity_type = 1
        activity.distance = 10000.0
        activity.total_timer_time = 3600.0
        activity.calories = 500

        result = calculate_activity_stats([activity])

        assert result.run.distance == 10000.0
        assert result.run.time == 3600.0
        assert result.run.calories == 500

    def test_calculate_stats_multiple_activities(self):
        from modules.activities.activity.stats import calculate_activity_stats

        run = MagicMock()
        run.activity_type = 1
        run.distance = 5000.0
        run.total_timer_time = 1800.0
        run.calories = 250

        bike = MagicMock()
        bike.activity_type = 4
        bike.distance = 30000.0
        bike.total_timer_time = 5400.0
        bike.calories = 800

        result = calculate_activity_stats([run, bike])

        assert result.run.distance == 5000.0
        assert result.bike.distance == 30000.0

    def test_calculate_stats_none_activities(self):
        from modules.activities.activity.stats import calculate_activity_stats

        result = calculate_activity_stats(None)

        assert result.run.distance == 0.0

    def test_calculate_stats_different_sports(self):
        from modules.activities.activity.stats import calculate_activity_stats

        swim = MagicMock()
        swim.activity_type = 8
        swim.distance = 1500.0
        swim.total_timer_time = 1800.0
        swim.calories = 300

        walk = MagicMock()
        walk.activity_type = 11
        walk.distance = 3000.0
        walk.total_timer_time = 2400.0
        walk.calories = 150

        result = calculate_activity_stats([swim, walk])

        assert result.swim.distance == 1500.0
        assert result.walk.distance == 3000.0


@pytest.mark.skip(reason="HealthFasting mapper circular import issue in test env")
class TestTransformSchemaToModel:
    def test_transform_basic(self):
        pass

    def test_transform_with_created_at(self):
        pass
