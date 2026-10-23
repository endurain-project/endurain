from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service

_PREFIX = "modules.health.health_fasting.service"
_CRUD = f"{_PREFIX}.health_fasting_crud"


def _complete(status: str = "completed", notes: str | None = None) -> health_fasting_schema.HealthFastingComplete:
    return health_fasting_schema.HealthFastingComplete(
        fast_end_time=datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC), status=status, notes=notes
    )


class TestGetHealthFasting:
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_returns_the_record(self, mock_get, mock_db):
        assert health_fasting_service.get_health_fasting(1, 5, mock_db) is mock_get.return_value
        mock_get.assert_called_once_with(5, 1, mock_db)

    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id", return_value=None)
    def test_missing_record_is_not_found(self, _get, mock_db):
        with pytest.raises(core_exceptions.NotFoundError, match="Fasting record not found"):
            health_fasting_service.get_health_fasting(1, 5, mock_db)


class TestCreateHealthFasting:
    @patch(f"{_CRUD}.create_health_fasting")
    @patch(f"{_CRUD}.get_active_fasting_by_user_id", return_value=None)
    def test_starts_a_fast_and_commits(self, _active, mock_create, mock_db):
        record = health_fasting_schema.HealthFastingCreate(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        assert health_fasting_service.create_health_fasting(1, record, mock_db) is mock_create.return_value
        mock_db.commit.assert_called_once()

    @patch(f"{_CRUD}.create_health_fasting")
    @patch(f"{_CRUD}.get_active_fasting_by_user_id")
    def test_refuses_a_second_active_fast(self, _active, mock_create, mock_db):
        record = health_fasting_schema.HealthFastingCreate(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        with pytest.raises(core_exceptions.InvalidInputError, match="already has an active fasting session"):
            health_fasting_service.create_health_fasting(1, record, mock_db)

        mock_create.assert_not_called()
        mock_db.commit.assert_not_called()


class TestEditAndDelete:
    def test_edit_rejects_a_record_of_another_user(self, mock_db):
        update = health_fasting_schema.HealthFastingUpdate(id=1, user_id=2)

        with pytest.raises(core_exceptions.PermissionDeniedError):
            health_fasting_service.edit_health_fasting(1, update, mock_db)
        mock_db.commit.assert_not_called()

    @patch(f"{_CRUD}.edit_health_fasting")
    def test_edit_commits(self, _edit, mock_db):
        health_fasting_service.edit_health_fasting(
            1, health_fasting_schema.HealthFastingUpdate(id=1, user_id=1), mock_db
        )

        mock_db.commit.assert_called_once()

    @patch(f"{_CRUD}.delete_health_fasting")
    def test_delete_commits(self, mock_delete, mock_db):
        health_fasting_service.delete_health_fasting(1, 5, mock_db)

        mock_delete.assert_called_once_with(1, 5, mock_db)
        mock_db.commit.assert_called_once()


class TestCompleteHealthFasting:
    @patch(f"{_CRUD}.end_health_fasting")
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_derives_the_duration_and_commits(self, mock_get, mock_end, mock_db):
        mock_get.return_value = MagicMock(status="in_progress", fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        health_fasting_service.complete_health_fasting(1, 5, _complete(notes="done"), mock_db)

        args = mock_end.call_args.args
        assert args[:2] == (1, 5)
        assert args[2] == datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC)
        assert args[3:6] == ("completed", 86400, "done")
        mock_db.commit.assert_called_once()

    @patch(f"{_CRUD}.end_health_fasting")
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_refuses_a_session_that_is_not_in_progress(self, mock_get, mock_end, mock_db):
        mock_get.return_value = MagicMock(status="completed", fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        with pytest.raises(core_exceptions.InvalidInputError, match="not in progress"):
            health_fasting_service.complete_health_fasting(1, 5, _complete(), mock_db)

        mock_end.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id", return_value=None)
    def test_unknown_session_is_not_found(self, _get, mock_db):
        with pytest.raises(core_exceptions.NotFoundError):
            health_fasting_service.complete_health_fasting(1, 5, _complete(), mock_db)

    @patch(f"{_CRUD}.end_health_fasting")
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_status_defaults_to_completed(self, mock_get, mock_end, mock_db):
        mock_get.return_value = MagicMock(status="in_progress", fast_start_time=datetime(2024, 1, 15, 8, 0, 0))
        complete = health_fasting_schema.HealthFastingComplete(fast_end_time=datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC))

        health_fasting_service.complete_health_fasting(1, 5, complete, mock_db)

        assert mock_end.call_args.args[3] == "completed"


class TestGetFastingStats:
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=date(2024, 1, 15))
    @patch(f"{_PREFIX}.users_integration.resolve_timezone", return_value="UTC")
    def test_combines_the_aggregates_streaks_and_completion_rate(self, _tz, _today, mock_db):
        with (
            patch(f"{_CRUD}.get_completed_fasting_count", return_value=3),
            patch(f"{_CRUD}.get_health_fasting_number_by_user_id", return_value=4),
            patch(f"{_CRUD}.get_avg_fasting_duration", return_value=50000),
            patch(f"{_CRUD}.get_total_fasting_seconds", return_value=150000),
            patch(
                f"{_CRUD}.get_completed_fasting_dates_by_user_id",
                return_value=[date(2024, 1, 13), date(2024, 1, 14), date(2024, 1, 15)],
            ),
        ):
            stats = health_fasting_service.get_fasting_stats(1, mock_db)

        assert (stats.total_fasts, stats.current_streak, stats.longest_streak) == (3, 3, 3)
        assert (stats.avg_duration_seconds, stats.total_fasting_seconds) == (50000, 150000)
        assert stats.completion_rate == 75.0

    @patch(f"{_PREFIX}.users_integration.local_today", return_value=date(2024, 1, 15))
    @patch(f"{_PREFIX}.users_integration.resolve_timezone", return_value="UTC")
    def test_completion_rate_is_zero_without_any_fast(self, _tz, _today, mock_db):
        with (
            patch(f"{_CRUD}.get_completed_fasting_count", return_value=0),
            patch(f"{_CRUD}.get_health_fasting_number_by_user_id", return_value=0),
            patch(f"{_CRUD}.get_avg_fasting_duration", return_value=None),
            patch(f"{_CRUD}.get_total_fasting_seconds", return_value=0),
            patch(f"{_CRUD}.get_completed_fasting_dates_by_user_id", return_value=[]),
        ):
            stats = health_fasting_service.get_fasting_stats(1, mock_db)

        assert (stats.completion_rate, stats.current_streak, stats.longest_streak) == (0.0, 0, 0)


class TestListHealthFasting:
    @patch(f"{_CRUD}.get_health_fasting_by_user_id", return_value=[])
    @patch(f"{_CRUD}.get_health_fasting_number_by_user_id", return_value=0)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=date(2024, 1, 15))
    def test_resolves_the_interval_in_the_users_calendar(self, _today, mock_number, mock_list, mock_db):
        result = health_fasting_service.list_health_fasting(1, mock_db, 2, 10, health_constants.Interval.LAST_30_DAYS)

        since = date(2023, 12, 16)
        mock_number.assert_called_once_with(1, mock_db, since)
        mock_list.assert_called_once_with(1, mock_db, 2, 10, since)
        assert (result.total, result.page_number, result.num_records) == (0, 2, 10)

    @patch(f"{_CRUD}.get_health_fasting_by_user_id", return_value=[])
    @patch(f"{_CRUD}.get_health_fasting_number_by_user_id", return_value=0)
    def test_no_interval_means_no_lower_bound(self, mock_number, mock_list, mock_db):
        health_fasting_service.list_health_fasting(1, mock_db)

        mock_number.assert_called_once_with(1, mock_db, None)
