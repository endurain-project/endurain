"""Tests for user goals date-window helpers."""

from datetime import datetime

import pytest

import core.exceptions as core_exceptions
import modules.users.users_goals.utils as user_goals_utils


class TestGetStartEndDateByInterval:
    """
    Test suite for get_start_end_date_by_interval function.
    """

    def test_get_dates_daily_interval(self):
        """Test date calculation for daily interval."""
        # Act
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "daily",
            "2024-01-15",
            "monday",
        )

        # Assert
        assert start == datetime(2024, 1, 15, 0, 0, 0)
        assert end == datetime(2024, 1, 15, 23, 59, 59)

    def test_get_dates_weekly_interval(self):
        """Test date calculation for weekly interval."""
        # Act
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "weekly",
            "2024-01-15",  # Monday
            "monday",
        )

        # Assert
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday

    def test_get_dates_weekly_interval_with_sunday_start(self):
        """Test weekly dates respect a Sunday first day."""
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "weekly",
            "2024-01-15",
            "sunday",
        )

        assert start == datetime(2024, 1, 14, 0, 0, 0)
        assert end == datetime(2024, 1, 20, 23, 59, 59)

    def test_get_dates_monthly_interval(self):
        """Test date calculation for monthly interval."""
        # Act
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "monthly",
            "2024-01-15",
            "monday",
        )

        # Assert
        assert start.day == 1
        assert start.month == 1
        assert end.month == 1

    def test_get_dates_yearly_interval(self):
        """Test date calculation for yearly interval."""
        # Act
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "yearly",
            "2024-06-15",
            "monday",
        )

        # Assert
        assert start == datetime(2024, 1, 1, 0, 0, 0)
        assert end == datetime(2024, 12, 31, 23, 59, 59)

    def test_get_dates_invalid_interval(self):
        """Test invalid interval raises exception."""
        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            user_goals_utils.get_start_end_date_by_interval(
                "invalid",
                "2024-01-15",
                "monday",
            )

        assert "Invalid interval" in exc_info.value.detail
