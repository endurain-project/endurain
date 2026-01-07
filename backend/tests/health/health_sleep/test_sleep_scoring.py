import pytest
from datetime import datetime
from unittest.mock import MagicMock

import health.health_sleep.sleep_scoring as sleep_scoring
import health.health_sleep.schema as health_sleep_schema


class TestCalculateSleepDurationHours:
    """
    Test suite for _calculate_sleep_duration_hours function.
    """

    def test_calculate_sleep_duration_hours_success(self):
        """
        Test converting seconds to hours.
        """
        # Act
        result = sleep_scoring._calculate_sleep_duration_hours(28800)

        # Assert
        assert result == 8.0

    def test_calculate_sleep_duration_hours_none(self):
        """
        Test converting None returns 0.
        """
        # Act
        result = sleep_scoring._calculate_sleep_duration_hours(None)

        # Assert
        assert result == 0.0


class TestCalculateStagePercentage:
    """
    Test suite for _calculate_stage_percentage function.
    """

    def test_calculate_stage_percentage_success(self):
        """
        Test calculating stage percentage.
        """
        # Act
        result = sleep_scoring._calculate_stage_percentage(7200, 28800)

        # Assert
        assert result == 25.0

    def test_calculate_stage_percentage_none_stage(self):
        """
        Test calculating stage percentage with None stage.
        """
        # Act
        result = sleep_scoring._calculate_stage_percentage(None, 28800)

        # Assert
        assert result == 0.0

    def test_calculate_stage_percentage_zero_total(self):
        """
        Test calculating stage percentage with zero total.
        """
        # Act
        result = sleep_scoring._calculate_stage_percentage(7200, 0)

        # Assert
        assert result == 0.0


class TestCalculateSleepScoreDuration:
    """
    Test suite for calculate_sleep_score_duration function.
    """

    def test_calculate_sleep_score_duration_optimal_8_hours(self):
        """
        Test duration score for optimal 8 hours sleep.
        """
        # Arrange
        start_time = datetime(2024, 1, 14, 22, 0, 0)
        end_time = datetime(2024, 1, 15, 6, 0, 0)
        total_seconds = 28800  # 8 hours

        # Act
        score, label = sleep_scoring.calculate_sleep_score_duration(
            start_time, end_time, total_seconds
        )

        # Assert
        assert score == 100
        assert label == "EXCELLENT"

    def test_calculate_sleep_score_duration_7_hours(self):
        """
        Test duration score for 7 hours sleep.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_score_duration(None, None, 25200)

        # Assert
        assert score == 90
        assert label == "EXCELLENT"

    def test_calculate_sleep_score_duration_6_hours(self):
        """
        Test duration score for 6 hours sleep.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_score_duration(None, None, 21600)

        # Assert
        assert score == 70
        assert label == "GOOD"

    def test_calculate_sleep_score_duration_5_hours(self):
        """
        Test duration score for 5 hours sleep.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_score_duration(None, None, 18000)

        # Assert
        assert score == 50
        assert label == "FAIR"

    def test_calculate_sleep_score_duration_4_hours(self):
        """
        Test duration score for 4 hours sleep (poor).
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_score_duration(None, None, 14400)

        # Assert
        assert label == "POOR"
        assert score < 50

    def test_calculate_sleep_score_duration_none(self):
        """
        Test duration score with None total_sleep_seconds.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_score_duration(None, None, None)

        # Assert
        assert score == 0
        assert label == "POOR"


class TestCalculateSleepScoreQuality:
    """
    Test suite for calculate_sleep_score_quality function.
    """

    def test_calculate_sleep_score_quality_optimal(self):
        """
        Test quality score with optimal sleep stages.
        """
        # Arrange
        total_seconds = 28800  # 8 hours
        deep_seconds = 5184  # 18%
        rem_seconds = 6480  # 22.5%
        light_seconds = 14400  # 50%
        awake_seconds = 720  # 2.5%

        # Act
        score, label = sleep_scoring.calculate_sleep_score_quality(
            deep_seconds,
            light_seconds,
            rem_seconds,
            awake_seconds,
            total_seconds,
        )

        # Assert
        assert score >= 90
        assert label == "EXCELLENT"

    def test_calculate_sleep_score_quality_none_total(self):
        """
        Test quality score with None total sleep.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_score_quality(
            None, None, None, None, None
        )

        # Assert
        assert score == 0
        assert label == "POOR"

    def test_calculate_sleep_score_quality_poor_stages(self):
        """
        Test quality score with poor sleep stage distribution.
        """
        # Arrange
        total_seconds = 28800
        deep_seconds = 1440  # 5% (too low)
        rem_seconds = 2880  # 10% (too low)
        light_seconds = 21600  # 75% (too high)
        awake_seconds = 2880  # 10% (too high)

        # Act
        score, label = sleep_scoring.calculate_sleep_score_quality(
            deep_seconds,
            light_seconds,
            rem_seconds,
            awake_seconds,
            total_seconds,
        )

        # Assert
        assert score < 70
        assert label in ["FAIR", "POOR"]


class TestCalculateAwakeCountScore:
    """
    Test suite for calculate_awake_count_score function.
    """

    def test_calculate_awake_count_score_zero(self):
        """
        Test awake count score with 0 awakenings.
        """
        # Act
        score, label = sleep_scoring.calculate_awake_count_score(0)

        # Assert
        assert score == 100
        assert label == "EXCELLENT"

    def test_calculate_awake_count_score_one(self):
        """
        Test awake count score with 1 awakening.
        """
        # Act
        score, label = sleep_scoring.calculate_awake_count_score(1)

        # Assert
        assert score == 95
        assert label == "EXCELLENT"

    def test_calculate_awake_count_score_three(self):
        """
        Test awake count score with 3 awakenings.
        """
        # Act
        score, label = sleep_scoring.calculate_awake_count_score(3)

        # Assert
        assert score == 79
        assert label == "GOOD"

    def test_calculate_awake_count_score_five(self):
        """
        Test awake count score with 5 awakenings.
        """
        # Act
        score, label = sleep_scoring.calculate_awake_count_score(5)

        # Assert
        assert score == 59
        assert label == "FAIR"

    def test_calculate_awake_count_score_many(self):
        """
        Test awake count score with many awakenings.
        """
        # Act
        score, label = sleep_scoring.calculate_awake_count_score(10)

        # Assert
        assert score < 50
        assert label == "POOR"

    def test_calculate_awake_count_score_none(self):
        """
        Test awake count score with None.
        """
        # Act
        score, label = sleep_scoring.calculate_awake_count_score(None)

        # Assert
        assert score == 50
        assert label == "FAIR"


class TestCalculateRemPercentageScore:
    """
    Test suite for calculate_rem_percentage_score function.
    """

    def test_calculate_rem_percentage_score_optimal(self):
        """
        Test REM percentage score with optimal value.
        """
        # Arrange
        total_seconds = 28800
        rem_seconds = 6480  # 22.5%

        # Act
        score, label = sleep_scoring.calculate_rem_percentage_score(
            rem_seconds, total_seconds
        )

        # Assert
        assert score >= 90
        assert label == "EXCELLENT"

    def test_calculate_rem_percentage_score_good(self):
        """
        Test REM percentage score with good value.
        """
        # Arrange
        total_seconds = 28800
        rem_seconds = 6048  # 21%

        # Act
        score, label = sleep_scoring.calculate_rem_percentage_score(
            rem_seconds, total_seconds
        )

        # Assert
        assert score >= 80
        assert label in ["EXCELLENT", "GOOD"]

    def test_calculate_rem_percentage_score_none_total(self):
        """
        Test REM percentage score with None total.
        """
        # Act
        score, label = sleep_scoring.calculate_rem_percentage_score(None, None)

        # Assert
        assert score == 0
        assert label == "POOR"


class TestCalculateDeepPercentageScore:
    """
    Test suite for calculate_deep_percentage_score function.
    """

    def test_calculate_deep_percentage_score_optimal(self):
        """
        Test deep percentage score with optimal value.
        """
        # Arrange
        total_seconds = 28800
        deep_seconds = 5184  # 18%

        # Act
        score, label = sleep_scoring.calculate_deep_percentage_score(
            deep_seconds, total_seconds
        )

        # Assert
        assert score >= 90
        assert label == "EXCELLENT"

    def test_calculate_deep_percentage_score_none_total(self):
        """
        Test deep percentage score with None total.
        """
        # Act
        score, label = sleep_scoring.calculate_deep_percentage_score(None, None)

        # Assert
        assert score == 0
        assert label == "POOR"


class TestCalculateLightPercentageScore:
    """
    Test suite for calculate_light_percentage_score function.
    """

    def test_calculate_light_percentage_score_optimal(self):
        """
        Test light percentage score with optimal value.
        """
        # Arrange
        total_seconds = 28800
        light_seconds = 14400  # 50%

        # Act
        score, label = sleep_scoring.calculate_light_percentage_score(
            light_seconds, total_seconds
        )

        # Assert
        assert score >= 90
        assert label == "EXCELLENT"

    def test_calculate_light_percentage_score_none_total(self):
        """
        Test light percentage score with None total.
        """
        # Act
        score, label = sleep_scoring.calculate_light_percentage_score(None, None)

        # Assert
        assert score == 0
        assert label == "POOR"


class TestCalculateSleepStressScore:
    """
    Test suite for calculate_sleep_stress_score function.
    """

    def test_calculate_sleep_stress_score_low_stress(self):
        """
        Test sleep stress score with low stress.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_stress_score(20, 2)

        # Assert
        assert score >= 90
        assert label in ["EXCELLENT", "GOOD"]

    def test_calculate_sleep_stress_score_medium_stress(self):
        """
        Test sleep stress score with medium stress.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_stress_score(60, 3)

        # Assert
        assert score >= 50
        assert label in ["GOOD", "FAIR"]

    def test_calculate_sleep_stress_score_high_stress(self):
        """
        Test sleep stress score with high stress.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_stress_score(85, 8)

        # Assert
        assert score < 50
        assert label == "POOR"

    def test_calculate_sleep_stress_score_none(self):
        """
        Test sleep stress score with None stress.
        """
        # Act
        score, label = sleep_scoring.calculate_sleep_stress_score(None, None)

        # Assert
        assert score == 50
        assert label == "FAIR"


class TestCalculateSleepScoreOverall:
    """
    Test suite for calculate_sleep_score_overall function.
    """

    def test_calculate_sleep_score_overall_excellent(self):
        """
        Test overall sleep score with excellent sleep.
        """
        # Arrange
        start_time = datetime(2024, 1, 14, 22, 0, 0)
        end_time = datetime(2024, 1, 15, 6, 0, 0)
        total_seconds = 28800  # 8 hours
        deep_seconds = 5184  # 18%
        light_seconds = 14400  # 50%
        rem_seconds = 6480  # 22.5%
        awake_seconds = 720  # 2.5%
        awake_count = 1
        restless_count = 2
        avg_stress = 20

        # Act
        score = sleep_scoring.calculate_sleep_score_overall(
            start_time,
            end_time,
            total_seconds,
            deep_seconds,
            light_seconds,
            rem_seconds,
            awake_seconds,
            awake_count,
            restless_count,
            avg_stress,
        )

        # Assert
        assert score >= 85
        assert score <= 100

    def test_calculate_sleep_score_overall_poor(self):
        """
        Test overall sleep score with poor sleep.
        """
        # Arrange
        start_time = datetime(2024, 1, 14, 23, 0, 0)
        end_time = datetime(2024, 1, 15, 3, 0, 0)
        total_seconds = 14400  # 4 hours
        deep_seconds = 1440  # 10%
        light_seconds = 10800  # 75%
        rem_seconds = 1440  # 10%
        awake_seconds = 720  # 5%
        awake_count = 8
        restless_count = 12
        avg_stress = 85

        # Act
        score = sleep_scoring.calculate_sleep_score_overall(
            start_time,
            end_time,
            total_seconds,
            deep_seconds,
            light_seconds,
            rem_seconds,
            awake_seconds,
            awake_count,
            restless_count,
            avg_stress,
        )

        # Assert
        assert score >= 0
        assert score < 50


class TestCalculateAndSetSleepScores:
    """
    Test suite for _calculate_and_set_sleep_scores function.
    """

    def test_calculate_and_set_sleep_scores_success(self):
        """
        Test calculating and setting all sleep scores.
        """
        # Arrange
        health_sleep = health_sleep_schema.HealthSleep(
            sleep_start_time_local=datetime(2024, 1, 14, 22, 0, 0),
            sleep_end_time_local=datetime(2024, 1, 15, 6, 0, 0),
            total_sleep_seconds=28800,
            deep_sleep_seconds=5184,
            light_sleep_seconds=14400,
            rem_sleep_seconds=6480,
            awake_sleep_seconds=720,
            awake_count=1,
            restless_moments_count=2,
            avg_sleep_stress=20,
        )

        # Act
        sleep_scoring._calculate_and_set_sleep_scores(health_sleep)

        # Assert
        assert health_sleep.sleep_score_overall is not None
        assert health_sleep.sleep_score_overall >= 0
        assert health_sleep.sleep_score_overall <= 100
        assert health_sleep.sleep_score_duration is not None
        assert health_sleep.sleep_score_quality is not None
        assert health_sleep.awake_count_score is not None
        assert health_sleep.rem_percentage_score is not None
        assert health_sleep.deep_percentage_score is not None
        assert health_sleep.light_percentage_score is not None
        assert health_sleep.sleep_stress_score is not None

    def test_calculate_and_set_sleep_scores_minimal_data(self):
        """
        Test calculating scores with minimal data.
        """
        # Arrange
        health_sleep = health_sleep_schema.HealthSleep(
            total_sleep_seconds=28800,
        )

        # Act
        sleep_scoring._calculate_and_set_sleep_scores(health_sleep)

        # Assert
        assert health_sleep.sleep_score_overall is not None
        assert health_sleep.sleep_score_duration is not None
        assert health_sleep.sleep_score_quality is not None
