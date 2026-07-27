"""Tests for ``activities.activity.stats`` aggregation."""

from unittest.mock import MagicMock, patch


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

    @patch("modules.activities.activity.stats.core_logger")
    def test_error_handling_bad_activity_type(self, mock_logger):
        """A malformed activity is logged and skipped rather than aborting the aggregate."""
        from modules.activities.activity.stats import calculate_activity_stats

        bad_activity = MagicMock()
        type(bad_activity).activity_type = property(lambda self: (_ for _ in ()).throw(TypeError("bad type")))

        calculate_activity_stats([bad_activity])

        mock_logger.print_to_log.assert_called_once()
