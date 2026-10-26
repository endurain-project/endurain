"""Tests for ``activities.activity.stats`` aggregation."""

from modules.activities.activity.contracts import ActivityTypeTotals
from modules.activities.activity.stats import calculate_activity_stats


class TestCalculateActivityStats:
    def test_a_total_lands_in_its_sport(self):
        result = calculate_activity_stats([ActivityTypeTotals(1, distance=10000.0, time=3600.0, calories=500.0)])

        assert result.run.distance == 10000.0
        assert result.run.time == 3600.0
        assert result.run.calories == 500.0

    def test_different_sports_stay_apart(self):
        result = calculate_activity_stats(
            [
                ActivityTypeTotals(1, distance=5000.0, time=1800.0, calories=250.0),
                ActivityTypeTotals(4, distance=30000.0, time=5400.0, calories=800.0),
                ActivityTypeTotals(8, distance=1500.0, time=1800.0, calories=300.0),
            ]
        )

        assert result.run.distance == 5000.0
        assert result.bike.distance == 30000.0
        assert result.swim.distance == 1500.0
        assert result.walk.distance == 0.0

    def test_activity_types_of_one_sport_add_up(self):
        """Run, trail run and virtual run are three activity types of the run sport."""
        run_types = [1, 2, 3]
        result = calculate_activity_stats(
            [ActivityTypeTotals(run_type, distance=1000.0, time=600.0, calories=50.0) for run_type in run_types]
        )

        assert result.run.distance == 3000.0
        assert result.run.time == 1800.0
        assert result.run.calories == 150.0

    def test_a_type_that_belongs_to_no_sport_is_left_out(self):
        result = calculate_activity_stats([ActivityTypeTotals(999, distance=1.0, time=1.0, calories=1.0)])

        assert result == calculate_activity_stats([])

    def test_no_totals_give_empty_stats(self):
        result = calculate_activity_stats([])

        assert result.run.distance == 0.0
        assert result.bike.time == 0.0
